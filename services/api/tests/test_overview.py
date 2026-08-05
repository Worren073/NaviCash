"""tests — Resumen del dashboard (GET /api/overview)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from apps.rates.models import ExchangeRate
from factories import SavingsGoalFactory, TransactionFactory, WalletFactory
from django.utils import timezone


@pytest.mark.django_db
class TestOverview:
    """GET /api/overview consolida la home."""

    URL = "/api/overview"

    def _seed_rate(self) -> None:
        """Siembra una tasa oficial para conversiones (100 VES/USD)."""
        if not ExchangeRate.objects.filter(source="oficial").exists():
            ExchangeRate.objects.create(
                source="oficial",
                currency="VES",
                promedio=Decimal("100.00"),
                rate_date=timezone.now(),
            )

    def test_returns_wallets_saldos(self, api_client) -> None:
        """Devuelve la suma de saldos de billeteras en USD."""
        WalletFactory(user=api_client.user, saldo=Decimal("50.00"), currency="USD")
        WalletFactory(user=api_client.user, saldo=Decimal("25.00"), currency="USD")
        resp = api_client.get(self.URL)
        assert resp.status_code == 200
        assert resp.data["total_balance_usd"] == "75.00"
        assert len(resp.data["wallets"]) == 2

    def test_returns_totals_pending(self, api_client) -> None:
        """Totales pendientes vencidos: por cobrar, por pagar y vencido."""
        self._seed_rate()
        # Un cobro vencido (30 USD) y un pago vencido (20 USD).
        TransactionFactory(
            user=api_client.user,
            tipo="cobro",
            monto=Decimal("30.00"),
            moneda="USD",
            monto_usd=Decimal("30.00"),
            fecha_vencimiento=date.today() - timedelta(days=1),
        )
        TransactionFactory(
            user=api_client.user,
            tipo="pago",
            monto=Decimal("20.00"),
            moneda="USD",
            monto_usd=Decimal("20.00"),
            fecha_vencimiento=date.today() - timedelta(days=1),
        )
        resp = api_client.get(self.URL)
        assert resp.data["to_receive"] == "30.00"
        assert resp.data["to_pay"] == "20.00"
        assert resp.data["overdue"] == "50.00"

    def test_upcoming_excludes_overdue(self, api_client) -> None:
        """Upcoming solo contiene operaciones futuras no vencidas."""
        TransactionFactory(
            user=api_client.user,
            fecha_vencimiento=date.today() - timedelta(days=1),  # vencida, no entra
        )
        TransactionFactory(
            user=api_client.user,
            fecha_vencimiento=date.today() + timedelta(days=3),  # próxima, sí
        )
        resp = api_client.get(self.URL)
        upcoming = resp.data["upcoming"]
        assert len(upcoming) == 1

    def test_requires_auth(self) -> None:
        """Sin token responde 401/403."""
        from rest_framework.test import APIClient

        resp = APIClient().get(self.URL)
        assert resp.status_code in (401, 403)


@pytest.mark.django_db
class TestCategoryBreakdown:
    """GET /api/overview/categories?kind=pago."""

    URL = "/api/overview/categories"

    def test_groups_by_category(self, api_client) -> None:
        """Agrupa pagos por categoría con total en moneda base."""
        from apps.transactions.models import Category

        cat = Category.objects.create(
            user=api_client.user, name="Supermercado", tipo="egreso", icon="cart"
        )
        TransactionFactory(
            user=api_client.user,
            tipo="pago",
            monto=Decimal("10.00"),
            moneda="USD",
            monto_usd=Decimal("10.00"),
            category=cat,
        )
        TransactionFactory(
            user=api_client.user,
            tipo="pago",
            monto=Decimal("5.00"),
            moneda="USD",
            monto_usd=Decimal("5.00"),
        )  # sin categoría
        resp = api_client.get(f"{self.URL}?kind=pago")
        assert resp.status_code == 200
        ordered = {row["category"]: row["total"] for row in resp.data}
        assert ordered["Supermercado"] == Decimal("10.00")
        assert ordered["Sin categoría"] == Decimal("5.00")

    def test_invalid_kind_rejected(self, api_client) -> None:
        """kind distinto de cobro/pago responde 400."""
        resp = api_client.get(f"{self.URL}?kind=otro")
        assert resp.status_code == 400