"""tests — Cuentas del negocio (VES/USD) y métodos de pago del CRM.

Cubre:
- Creación de las DOS cuentas del negocio (principal/secundaria) y su exposición
  vía ``GET /api/business``.
- Método de pago → moneda del documento → cuenta donde entra/sale el dinero.
- Equivalencia: parte pagada CONGELADA con la tasa del día y saldo con la tasa
  ACTUAL (regla B de Worren).
- Pedidos espejo de las facturas.
- Transferencia VES↔USD entre las cuentas del negocio.
- Resumen del dashboard que agrega ambas cuentas en la moneda base.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.utils import timezone

from apps.business.services import build_business_summary, create_business
from apps.core.exceptions import BusinessRuleError
from apps.crm.models import BusinessContact
from apps.crm.services import create_invoice, create_order, record_invoice_payment
from apps.rates.models import ExchangeRate
from apps.transactions.services import create_transfer
from factories import WalletFactory


def _seed_rate(value: str = "100.00") -> ExchangeRate:
    """Crea una nueva tasa oficial (la más reciente manda en las conversiones)."""
    return ExchangeRate.objects.create(
        source="oficial",
        currency="VES",
        promedio=Decimal(value),
        rate_date=timezone.now(),
    )


@pytest.fixture(autouse=True)
def _official_rate() -> None:
    """Siembra la tasa oficial (100 VES/USD) si aún no existe."""
    if not ExchangeRate.objects.filter(source="oficial", currency="VES").exists():
        _seed_rate("100.00")


def _contact(api_client, business, *, kind: str = "cliente") -> BusinessContact:
    return BusinessContact.objects.create(
        user=api_client.user,
        business=business,
        name="Contacto A",
        type=kind,
        payment_terms_days=0,
    )


@pytest.mark.django_db
class TestBusinessAccounts:
    """La moneda base define cuál cuenta es la principal."""

    def test_create_business_usd_creates_two_accounts(self, api_client) -> None:
        business = create_business(
            api_client.user, name="Negocio", currency="USD", initial_capital=Decimal("500")
        )
        assert business.wallet.currency == "USD"
        assert business.wallet.name == "Negocio-USD"
        assert business.wallet.role == "primary"
        assert business.wallet.saldo == Decimal("500.00")
        assert business.secondary_wallet.currency == "VES"
        assert business.secondary_wallet.name == "Negocio-VES"
        assert business.secondary_wallet.role == "secondary"
        assert business.secondary_wallet.saldo == Decimal("0.00")
        assert business.wallets.count() == 2

    def test_create_business_ves_creates_two_accounts(self, api_client) -> None:
        business = create_business(
            api_client.user, name="Bodega", currency="VES", initial_capital=Decimal("1000")
        )
        assert business.wallet.currency == "VES"
        assert business.wallet.name == "Bodega-VES"
        assert business.wallet.saldo == Decimal("1000.00")
        assert business.secondary_wallet.currency == "USD"
        assert business.secondary_wallet.name == "Bodega-USD"
        assert business.secondary_wallet.saldo == Decimal("0.00")

    def test_get_business_exposes_accounts(self, api_client) -> None:
        business = create_business(
            api_client.user, name="Tienda", currency="USD", initial_capital=Decimal("50")
        )
        resp = api_client.get("/api/business")
        assert resp.status_code == 200
        assert resp.data["wallet_id"] == str(business.wallet.pk)
        assert resp.data["saldo"] == "50.00"
        accounts = {row["currency"]: row for row in resp.data["accounts"]}
        assert set(accounts) == {"USD", "VES"}
        assert accounts["USD"]["role"] == "primary"
        assert accounts["USD"]["balance"] == "50.00"
        assert accounts["USD"]["name"] == "Tienda-USD"
        assert accounts["VES"]["role"] == "secondary"

    def test_wallets_endpoint_exposes_role(self, api_client) -> None:
        create_business(
            api_client.user, name="Tienda", currency="USD", initial_capital=Decimal("0")
        )
        resp = api_client.get("/api/wallets?scope=business")
        rows = resp.data["results"]
        assert len(rows) == 2
        assert {row["role"] for row in rows} == {"primary", "secondary"}


@pytest.mark.django_db
class TestPaymentMethodRouting:
    """El método de pago define la moneda del documento y la cuenta."""

    def _business(self, api_client, currency: str = "USD"):
        return create_business(
            api_client.user, name="Negocio", currency=currency, initial_capital=Decimal("0")
        )

    def test_invoice_ves_method_credits_ves_account(self, api_client) -> None:
        business = self._business(api_client, "USD")
        contact = _contact(api_client, business)
        invoice = create_invoice(
            api_client.user,
            business,
            contact,
            [{"description": "Servicio", "quantity": 2, "unit_price": "100.00"}],
            payment_method="pago_movil",
            paid_amount=Decimal("200.00"),
        )
        assert invoice.currency == "VES"
        assert invoice.status == "pagada"
        business.wallet.refresh_from_db()
        business.secondary_wallet.refresh_from_db()
        assert business.wallet.saldo == Decimal("0.00")
        assert business.secondary_wallet.saldo == Decimal("200.00")
        payment = invoice.payments.get()
        assert payment.paid_currency == "VES"
        assert payment.paid_amount == Decimal("200.00")
        assert payment.payment_method == "pago_movil"

    def test_invoice_default_method_follows_business_currency(self, api_client) -> None:
        business = self._business(api_client, "USD")
        contact = _contact(api_client, business)
        invoice = create_invoice(
            api_client.user,
            business,
            contact,
            [{"description": "Producto", "quantity": 1, "unit_price": "50.00"}],
            paid_amount=Decimal("50.00"),
        )
        assert invoice.currency == "USD"
        business.wallet.refresh_from_db()
        assert business.wallet.saldo == Decimal("50.00")

    def test_order_ves_method_debits_ves_account(self, api_client) -> None:
        business = self._business(api_client, "USD")
        ves_wallet = business.secondary_wallet
        ves_wallet.saldo = Decimal("500.00")
        ves_wallet.save()
        contact = _contact(api_client, business, kind="proveedor")
        order = create_order(
            api_client.user,
            business,
            contact,
            [{"description": "Mercancía", "quantity": 2, "unit_price": "50.00"}],
            payment_method="pago_movil",
            paid_amount=Decimal("100.00"),
        )
        assert order.currency == "VES"
        business.secondary_wallet.refresh_from_db()
        business.wallet.refresh_from_db()
        assert business.secondary_wallet.saldo == Decimal("400.00")
        assert business.wallet.saldo == Decimal("0.00")

@pytest.mark.django_db
class TestEquivalence:
    """Regla B: pagado congelado, saldo con la tasa del día."""

    def test_partial_payment_freezes_paid_and_live_balance(self, api_client) -> None:
        _seed_rate("100.00")
        business = create_business(
            api_client.user, name="Negocio", currency="USD", initial_capital=Decimal("0")
        )
        contact = _contact(api_client, business)
        invoice = create_invoice(
            api_client.user,
            business,
            contact,
            [{"description": "Servicio", "quantity": 1, "unit_price": "250.00"}],
            payment_method="zelle",
        )
        assert invoice.currency == "USD"

        record_invoice_payment(invoice, Decimal("100.00"), payment_method="pago_movil")
        business.secondary_wallet.refresh_from_db()
        assert business.secondary_wallet.saldo == Decimal("10000.00")
        payment = invoice.payments.get()
        assert payment.paid_currency == "VES"
        assert payment.paid_amount == Decimal("10000.00")
        assert payment.rate_usd == Decimal("100.0000")

        resp = api_client.get(f"/api/business/invoices/{invoice.id}/")
        conversion = resp.data["conversion"]
        assert conversion["currency"] == "VES"
        assert conversion["frozen"] is False
        assert Decimal(conversion["paid"]) == Decimal("10000.00")
        assert Decimal(conversion["balance"]) == Decimal("15000.00")
        assert Decimal(conversion["total"]) == Decimal("25000.00")

        # Sube la tasa: lo pagado sigue congelado, el saldo se recalcula.
        _seed_rate("200.00")
        resp = api_client.get(f"/api/business/invoices/{invoice.id}/")
        conversion = resp.data["conversion"]
        assert Decimal(conversion["paid"]) == Decimal("10000.00")
        assert Decimal(conversion["balance"]) == Decimal("30000.00")
        assert Decimal(conversion["total"]) == Decimal("40000.00")

        # Paga el resto: la equivalencia total queda congelada.
        record_invoice_payment(invoice, Decimal("150.00"), payment_method="pago_movil")
        _seed_rate("300.00")
        resp = api_client.get(f"/api/business/invoices/{invoice.id}/")
        conversion = resp.data["conversion"]
        assert conversion["frozen"] is True
        assert Decimal(conversion["paid"]) == Decimal("40000.00")
        assert Decimal(conversion["balance"]) == Decimal("0.00")
        assert Decimal(conversion["total"]) == Decimal("40000.00")


@pytest.mark.django_db
class TestBusinessSummaryAccounts:
    """El resumen agrega principal + secundaria en la moneda base."""

    def test_summary_sums_both_accounts(self, api_client) -> None:
        _seed_rate("100.00")
        business = create_business(
            api_client.user, name="Negocio", currency="USD", initial_capital=Decimal("200")
        )
        ves_wallet = business.secondary_wallet
        ves_wallet.saldo = Decimal("10000.00")  # 100 USD a tasa 100
        ves_wallet.save()
        summary = build_business_summary(business)
        assert Decimal(summary["saldo"]) == Decimal("300.00")
        assert {row["currency"] for row in summary["accounts"]} == {"USD", "VES"}


@pytest.mark.django_db
class TestBusinessTransfer:
    """Transferencia VES↔USD entre las cuentas del negocio."""

    def test_transfer_between_business_accounts(self, api_client) -> None:
        _seed_rate("100.00")
        business = create_business(
            api_client.user, name="Negocio", currency="USD", initial_capital=Decimal("100")
        )
        create_transfer(
            business.wallet,
            business.secondary_wallet,
            Decimal("10.00"),
            rate_fuente="oficial",
        )
        business.wallet.refresh_from_db()
        business.secondary_wallet.refresh_from_db()
        assert business.wallet.saldo == Decimal("90.00")
        assert business.secondary_wallet.saldo == Decimal("1000.00")

    def test_transfer_business_to_personal_still_blocked(self, api_client) -> None:
        business = create_business(
            api_client.user, name="Negocio", currency="USD", initial_capital=Decimal("100")
        )
        personal = WalletFactory(user=api_client.user, currency="USD", saldo=Decimal("1.00"))
        with pytest.raises(BusinessRuleError):
            create_transfer(business.wallet, personal, Decimal("10.00"))
