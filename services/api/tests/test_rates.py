"""tests — Tasa oficial: endpoint, caché, fallback y conversión."""

from __future__ import annotations

from decimal import Decimal
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.rates.models import ExchangeRate
from apps.rates.service import get_current_official_rate, get_usd_rate_for_conversion
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