"""tests — Analíticas financieras del negocio (GET /api/business/analytics)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, time as dtime
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.business.models import Business
from apps.business.services import create_business
from apps.crm.models import (
    BusinessContact,
    Invoice,
    InvoicePayment,
    Order,
    OrderPayment,
    Product,
)
from apps.rates.models import ExchangeRate
from apps.transactions.models import Category
from factories import TransactionFactory


@pytest.fixture(autouse=True)
def _seed_rate() -> None:
    """Siembra la tasa oficial (100 VES/USD) para conversiones de la serie."""
    if not ExchangeRate.objects.filter(source="oficial").exists():
        ExchangeRate.objects.create(
            source="oficial",
            currency="VES",
            promedio=Decimal("100.00"),
            rate_date=timezone.now(),
        )


def _create_business(api_client, *, name="Analíticas SA", currency="USD"):
    return create_business(
        api_client.user, name=name, currency=currency, initial_capital=Decimal("0")
    )


def _month_start(offset: int) -> date:
    """Primer día del mes ``offset`` meses antes del actual (0 = este mes)."""
    today = date.today()
    total = today.year * 12 + (today.month - 1) - offset
    return date(total // 12, total % 12 + 1, 1)


@staticmethod
def _aware(d: date) -> datetime:
    return timezone.make_aware(datetime.combine(d, dtime.min))


@pytest.mark.django_db
class TestBusinessAnalyticsPnl:
    """Serie mensual P&L: solo la billetera del negocio, solo pagados."""

    def test_pnl_monthly_series(self, api_client) -> None:
        _create_business(api_client)
        wallet = Business.objects.get(user=api_client.user).wallet
        today = date.today()
        current = _month_start(0)
        previous = _month_start(1)
        # Este mes: un cobro y un pago.
        TransactionFactory(
            user=api_client.user, wallet=wallet, tipo="cobro", estado="pagado",
            monto=Decimal("40.00"), moneda="USD", monto_usd=Decimal("40.00"),
            fecha_pagado=_aware(current), fecha=today,
        )
        TransactionFactory(
            user=api_client.user, wallet=wallet, tipo="pago", estado="pagado",
            monto=Decimal("15.00"), moneda="USD", monto_usd=Decimal("15.00"),
            fecha_pagado=_aware(current), fecha=today,
        )
        # Mes anterior: otro cobro.
        TransactionFactory(
            user=api_client.user, wallet=wallet, tipo="cobro", estado="pagado",
            monto=Decimal("100.00"), moneda="USD", monto_usd=Decimal("100.00"),
            fecha_pagado=_aware(previous), fecha=previous,
        )
        resp = api_client.get("/api/business/analytics?months=6")
        assert resp.status_code == 200
        data = resp.data
        assert data["currency"] == "USD"
        assert data["months"] == 6
        assert len(data["pnl"]) == 6
        current_row = data["pnl"][-1]
        assert current_row["month"] == today.strftime("%Y-%m")
        assert current_row["income"] == 40.0
        assert current_row["expense"] == 15.0
        assert current_row["net"] == 25.0
        assert data["pnl"][-2]["income"] == 100.0
        assert data["pnl"][-2]["expense"] == 0.0

    def test_excludes_pending_transfers_and_other_worlds(
        self, api_client, auth_client_factory
    ) -> None:
        _create_business(api_client)
        wallet = Business.objects.get(user=api_client.user).wallet
        today = date.today()
        # Pendiente: no cuenta.
        TransactionFactory(
            user=api_client.user, wallet=wallet, tipo="cobro", estado="pendiente",
            monto=Decimal("999.00"), moneda="USD", monto_usd=Decimal("999.00"),
        )
        # Transferencia tipo transferencia: no es cobro ni pago del negocio.
        TransactionFactory(
            user=api_client.user, wallet=wallet, tipo="transferencia", estado="pagado",
            monto=Decimal("500.00"), moneda="USD", monto_usd=Decimal("500.00"),
            monto_destino=Decimal("500.00"), moneda_destino="USD",
            fecha_pagado=_aware(_month_start(0)), fecha=today,
        )
        # Billetera personal del mismo usuario: no entra en el tablero.
        from factories import WalletFactory

        personal = WalletFactory(user=api_client.user, saldo=Decimal("10.00"), currency="USD")
        TransactionFactory(
            user=api_client.user, wallet=personal, tipo="cobro", estado="pagado",
            monto=Decimal("777.00"), moneda="USD", monto_usd=Decimal("777.00"),
            fecha_pagado=_aware(_month_start(0)), fecha=today,
        )
        # Otro usuario: jamás.
        other = auth_client_factory()
        _create_business(other, name="Ajeno SA")
        other_wallet = Business.objects.get(user=other.user).wallet
        TransactionFactory(
            user=other.user, wallet=other_wallet, tipo="cobro", estado="pagado",
            monto=Decimal("888.00"), moneda="USD", monto_usd=Decimal("888.00"),
            fecha_pagado=_aware(_month_start(0)), fecha=today,
        )
        resp = api_client.get("/api/business/analytics?months=6")
        assert resp.status_code == 200
        current_row = resp.data["pnl"][-1]
        assert current_row["income"] == 0.0
        assert current_row["expense"] == 0.0
        # La ventana (no pendientes) no arrastra categorías fantasma.
        assert resp.data["incomeCategories"] == []
        assert resp.data["expenseCategories"] == []

    def test_categories_grouped_with_sin_categoria(self, api_client) -> None:
        _create_business(api_client)
        wallet = Business.objects.get(user=api_client.user).wallet
        today = date.today()
        ventas = Category.objects.create(
            user=api_client.user, name="Ventas", icon="trending-up", tipo="ingreso"
        )
        insumos = Category.objects.create(
            user=api_client.user, name="Insumos", icon="box", tipo="egreso"
        )
        TransactionFactory(
            user=api_client.user, wallet=wallet, tipo="cobro", estado="pagado",
            monto=Decimal("30.00"), moneda="USD", monto_usd=Decimal("30.00"),
            fecha_pagado=_aware(_month_start(0)), fecha=today, category=ventas,
        )
        # Sin categoría pero mayor monto: debe quedar primero en la lista.
        TransactionFactory(
            user=api_client.user, wallet=wallet, tipo="cobro", estado="pagado",
            monto=Decimal("70.00"), moneda="USD", monto_usd=Decimal("70.00"),
            fecha_pagado=_aware(_month_start(0)), fecha=today,
        )
        TransactionFactory(
            user=api_client.user, wallet=wallet, tipo="pago", estado="pagado",
            monto=Decimal("12.00"), moneda="USD", monto_usd=Decimal("12.00"),
            fecha_pagado=_aware(_month_start(0)), fecha=today, category=insumos,
        )
        resp = api_client.get("/api/business/analytics")
        data = resp.data
        assert data["incomeCategories"] == [
            {"label": "Sin categoría", "value": 70.0},
            {"label": "Ventas", "value": 30.0},
        ]
        assert data["expenseCategories"] == [{"label": "Insumos", "value": 12.0}]


@pytest.mark.django_db
class TestBusinessAnalyticsCrm:
    """Aging, KPIs y top clientes/proveedores desde el CRM."""

    @pytest.fixture
    def company(self, api_client):
        return _create_business(api_client)

    def _contact(self, api_client, company, name="Cliente A", ctype="cliente"):
        return BusinessContact.objects.create(
            user=api_client.user, business=company, name=name, type=ctype
        )

    def test_aging_receivable_overdue(self, api_client, company) -> None:
        today = timezone.localdate()
        contact = self._contact(api_client, company)
        # Factura vencida hace 45 días: bucket 31-60, suma al overdue.
        Invoice.objects.create(
            user=api_client.user, business=company, contact=contact,
            number="F-00001", issue_date=today - timedelta(days=60),
            due_date=today - timedelta(days=45), status="parcial",
            subtotal=Decimal("500.00"), tax_amount=Decimal("0.00"),
            total=Decimal("500.00"), amount_paid=Decimal("100.00"),
            balance_due=Decimal("400.00"), currency="USD",
        )
        # Factura aún no vencida: bucket 0-30, no cuenta como overdue.
        Invoice.objects.create(
            user=api_client.user, business=company, contact=contact,
            number="F-00002", issue_date=today, due_date=today + timedelta(days=10),
            status="enviada", subtotal=Decimal("1000.00"), tax_amount=Decimal("0.00"),
            total=Decimal("1000.00"), amount_paid=Decimal("0.00"),
            balance_due=Decimal("1000.00"), currency="USD",
        )
        # Factura pagada: sale de cuentas por cobrar.
        Invoice.objects.create(
            user=api_client.user, business=company, contact=contact,
            number="F-00003", issue_date=today, due_date=today,
            status="pagada", subtotal=Decimal("50.00"), tax_amount=Decimal("0.00"),
            total=Decimal("50.00"), amount_paid=Decimal("50.00"),
            balance_due=Decimal("0.00"), currency="USD",
        )
        resp = api_client.get("/api/business/analytics")
        data = resp.data
        aging = {row["bucket"]: row["value"] for row in data["aging"]}
        assert aging == {"0_30": 1000.0, "31_60": 400.0, "61_90": 0.0, "90": 0.0}
        assert data["kpis"]["receivable"] == 1400.0
        assert data["kpis"]["overdue"] == 400.0

    def test_payable_and_inventory_value(self, api_client, company) -> None:
        today = timezone.localdate()
        supplier = self._contact(api_client, company, name="Proveedor X", ctype="proveedor")
        Order.objects.create(
            user=api_client.user, business=company, contact=supplier,
            number="P-00001", order_date=today, status="en_camino",
            subtotal=Decimal("200.00"), shipping_amount=Decimal("0.00"),
            total=Decimal("200.00"), amount_paid=Decimal("0.00"),
            balance_due=Decimal("200.00"), currency="USD",
        )
        Product.objects.create(
            user=api_client.user, business=company, name="Café 1kg",
            unit_price=Decimal("25.00"), cost_price=Decimal("15.00"),
            stock_quantity=Decimal("3"), category=None,
        )
        Product.objects.create(
            user=api_client.user, business=company, name="Filtros",
            unit_price=Decimal("5.00"), cost_price=None, stock_quantity=Decimal("10"),
            category=None,
        )
        resp = api_client.get("/api/business/analytics")
        data = resp.data
        assert data["kpis"]["payable"] == 200.0
        # 3x15 + 10x0 (cost_price nulo) = 45.
        assert data["kpis"]["inventoryValue"] == 45.0

    def test_top_clients_and_suppliers(self, api_client, company) -> None:
        today = timezone.localdate()
        client_a = self._contact(api_client, company, name="Cliente A")
        client_b = self._contact(api_client, company, name="Cliente B")
        supplier = self._contact(api_client, company, name="Proveedor X", ctype="proveedor")
        for contact, number, amount, days_ago in (
            (client_a, "F-00001", Decimal("300.00"), 1),
            (client_b, "F-00002", Decimal("150.00"), 5),
            (client_a, "F-00003", Decimal("80.00"), 10),
        ):
            invoice = Invoice.objects.create(
                user=api_client.user, business=company, contact=contact,
                number=number, issue_date=today, due_date=today,
                status="pagada", subtotal=amount, tax_amount=Decimal("0.00"),
                total=amount, amount_paid=amount, balance_due=Decimal("0.00"),
                currency="USD",
            )
            InvoicePayment.objects.create(
                user=api_client.user, invoice=invoice, amount=amount,
                paid_at=_aware(today - timedelta(days=days_ago)),
            )
        order = Order.objects.create(
            user=api_client.user, business=company, contact=supplier,
            number="P-00001", order_date=today, status="recibido",
            subtotal=Decimal("500.00"), shipping_amount=Decimal("0.00"),
            total=Decimal("500.00"), amount_paid=Decimal("500.00"),
            balance_due=Decimal("0.00"), currency="USD",
        )
        OrderPayment.objects.create(
            user=api_client.user, order=order, amount=Decimal("500.00"),
            paid_at=_aware(today - timedelta(days=2)),
        )
        resp = api_client.get("/api/business/analytics")
        data = resp.data
        assert data["topClients"] == [
            {"label": "Cliente A", "value": 380.0},
            {"label": "Cliente B", "value": 150.0},
        ]
        assert data["topSuppliers"] == [{"label": "Proveedor X", "value": 500.0}]

    def test_margin_pct(self, api_client) -> None:
        _create_business(api_client)
        wallet = Business.objects.get(user=api_client.user).wallet
        today = date.today()
        TransactionFactory(
            user=api_client.user, wallet=wallet, tipo="cobro", estado="pagado",
            monto=Decimal("100.00"), moneda="USD", monto_usd=Decimal("100.00"),
            fecha_pagado=_aware(_month_start(0)), fecha=today,
        )
        TransactionFactory(
            user=api_client.user, wallet=wallet, tipo="pago", estado="pagado",
            monto=Decimal("40.00"), moneda="USD", monto_usd=Decimal("40.00"),
            fecha_pagado=_aware(_month_start(0)), fecha=today,
        )
        resp = api_client.get("/api/business/analytics")
        assert resp.data["kpis"]["marginPct"] == 60.0
        assert resp.data["kpis"]["incomePeriod"] == 100.0
        assert resp.data["kpis"]["expensePeriod"] == 40.0


@pytest.mark.django_db
class TestBusinessAnalyticsGuard:
    """Validación del endpoint."""

    def test_404_without_business(self, api_client) -> None:
        resp = api_client.get("/api/business/analytics")
        assert resp.status_code == 404

    def test_months_clamped(self, api_client) -> None:
        _create_business(api_client)
        resp = api_client.get("/api/business/analytics?months=99")
        assert resp.status_code == 200
        assert resp.data["months"] == 24
        assert len(resp.data["pnl"]) == 24
        assert api_client.get("/api/business/analytics?months=2").data["months"] == 3
        assert api_client.get("/api/business/analytics?months=abc").data["months"] == 12
        assert api_client.get("/api/business/analytics").data["months"] == 12