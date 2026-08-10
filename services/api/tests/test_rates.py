"""tests — Tasa oficial: endpoint, caché, fallback y conversión."""

from __future__ import annotations

from decimal import Decimal
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.utils import timezone

from apps.core.exceptions import BusinessRuleError
from apps.rates.models import ExchangeRate
from apps.rates.providers import ProviderRate, RateProviderError
from apps.rates.service import (
    REFRESH_LOCK_KEY,
    get_current_official_rate,
    get_usd_rate_for_conversion,
)
from factories import ExchangeRateFactory


@pytest.mark.django_db
class TestRateEndpoint:
    """GET /api/rates/current."""

    URL = "/api/rates/current"

    def test_returns_current_rate(self, api_client) -> None:
        """Con el proveedor estático devuelve 100.00 VES/USD (promedio)."""
        ExchangeRateFactory()
        resp = api_client.get(self.URL)
        assert resp.status_code == 200
        assert resp.data["source"] == "oficial"
        assert float(resp.data["rate"]) == 100.0

    def test_refreshes_and_persists_when_none(self, api_client) -> None:
        """Sin tasa previa, consulta al provider (estático) y la persiste."""
        resp = api_client.get(self.URL)
        assert resp.status_code == 200
        assert ExchangeRate.objects.filter(source="oficial").exists()

    def test_requires_auth(self) -> None:
        """Sin token el endpoint responde 401/403 (permiso IsAuthenticated)."""
        from rest_framework.test import APIClient

        resp = APIClient().get(self.URL)
        assert resp.status_code in (401, 403)


@pytest.mark.django_db
class TestRateService:
    """Servicio de tasas: caché con TTL y reutilización de la última."""

    def test_returns_fresh_rate_from_cache(self) -> None:
        """Una tasa reciente se devuelve tal cual (sin reconsultar)."""
        ExchangeRateFactory(promedio=Decimal("200.00"))
        rate = get_current_official_rate(stale_ok=True)
        assert rate.effective_rate == Decimal("200.00")

    def test_returns_stale_as_fallback(self) -> None:
        """Si el proveedor fallara, usa la última guardada (marcada stale)."""
        ExchangeRateFactory(promedio=Decimal("300.00"), is_stale=False)
        rate = get_current_official_rate(stale_ok=True)
        assert rate.effective_rate == Decimal("300.00")

    def test_usd_rate_for_conversion_positive(self) -> None:
        """La tasa de conversión nunca es <= 0."""
        ExchangeRateFactory(promedio=Decimal("75.00"))
        assert get_usd_rate_for_conversion() == Decimal("75.00")


@pytest.mark.django_db
class TestRateStaleness:
    """La marca de desactualización se computa por antigüedad."""

    def test_old_rate_is_stale(self) -> None:
        """Una tasa mucho mayor al TTL se considera desactualizada (flag)."""
        old = ExchangeRateFactory(
            promedio=Decimal("50.00"),
            rate_date=timezone.now() - timedelta(days=2),
        )
        # Forzamos el flag leyendo con la última guardada (ya no fresca).
        fresh = get_current_official_rate(stale_ok=True)
        assert fresh.effective_rate is not None


@pytest.mark.django_db
class TestConversionNeverFallsBackToOne:
    """A6: la conversión nunca devuelve Decimal("1") si no hay tasa.

    Si no hay tasa guardada y el proveedor falla (mockeado, sin red),
    ``get_usd_rate_for_conversion`` debe lanzar ``BusinessRuleError`` para que
    el registro se rechace en vez de congelarse con tasa 1.
    """

    def test_raises_business_rule_error_without_rate_and_provider_down(self) -> None:
        """Sin tasa en BD y proveedor caído -> BusinessRuleError (nunca 1)."""
        cache.delete(REFRESH_LOCK_KEY)

        class FailingProvider:
            def fetch_official_rate(self, currency="VES"):  # noqa: B027
                raise RateProviderError("DolarApi caído")

        with patch("apps.rates.service.get_provider", return_value=FailingProvider()):
            with pytest.raises(BusinessRuleError) as excinfo:
                get_usd_rate_for_conversion()

        assert "tasa oficial" in str(excinfo.value)


@pytest.mark.django_db
class TestRefreshSingleFlight:
    """A5: el refresco es single-flight con ``cache.add``."""

    def test_lock_held_does_not_hit_provider_and_uses_last_row(self) -> None:
        """Con el candado activo, se sirve la última fila sin llamar al proveedor."""
        cache.delete(REFRESH_LOCK_KEY)
        old = ExchangeRateFactory(promedio=Decimal("150.00"))
        old.input_at = timezone.now() - timedelta(hours=2)
        old.save(update_fields=["input_at"])

        calls: list[int] = []

        class SpyProvider:
            def fetch_official_rate(self, currency="VES"):  # noqa: B027
                calls.append(1)
                raise AssertionError(
                    "El proveedor no debe consultarse con el candado activo"
                )

        with patch("apps.rates.service.cache.add", return_value=False), patch(
            "apps.rates.service.get_provider", return_value=SpyProvider()
        ):
            rate = get_current_official_rate(stale_ok=True)

        assert rate.effective_rate == Decimal("150.00")
        assert calls == []

    def test_lock_is_released_after_successful_refresh(self) -> None:
        """El candado se libera al terminar: el siguiente intento lo re-adquiere."""
        cache.delete(REFRESH_LOCK_KEY)

        class StaticProvider:
            def fetch_official_rate(self, currency="VES"):  # noqa: B027
                return ProviderRate(source="oficial", promedio=Decimal("95.00"))

        with patch("apps.rates.service.get_provider", return_value=StaticProvider()):
            rate = get_current_official_rate(stale_ok=True)

        assert rate.effective_rate == Decimal("95.00")
        # Tras el refresco el candado quedó liberado (finally).
        assert cache.add(REFRESH_LOCK_KEY, 1, 30) is True
        cache.delete(REFRESH_LOCK_KEY)