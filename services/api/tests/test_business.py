"""tests — Módulo de negocio: creación, resumen y segregación personal/business."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.business.models import Business
from apps.core.exceptions import BusinessRuleError
from apps.rates.models import ExchangeRate
from apps.transactions.models import Transaction
from apps.transactions.services import create_transfer
from apps.wallets.models import Wallet
from factories import TransactionFactory, WalletFactory


@pytest.fixture(autouse=True)
def _seed_rate() -> None:
    """Siembra la tasa oficial (100 VES/USD) para conversiones del resumen."""
    if not ExchangeRate.objects.filter(source="oficial").exists():
        ExchangeRate.objects.create(
            source="oficial",
            currency="VES",
            promedio=Decimal("100.00"),
            rate_date=timezone.now(),
        )


def _create_business(api_client, *, name="Mi Cafetería", currency="USD", initial_capital="0.00"):
    """POST /api/business y assert de éxito; devuelve la respuesta."""
    resp = api_client.post(
        "/api/business",
        {"name": name, "currency": currency, "initial_capital": initial_capital},
    )
    assert resp.status_code == 201, resp.data
    return resp.data


def _business_wallet(api_client) -> Wallet:
    """Billetera del negocio del usuario (debe existir)."""
    return Business.objects.get(user=api_client.user).wallet


@pytest.mark.django_db
class TestBusinessCreate:
    """POST /api/business y GET /api/business."""

    def test_creates_business_and_business_wallet(self, api_client) -> None:
        data = _create_business(api_client, initial_capital="150.50")
        assert data["name"] == "Mi Cafetería"
        assert data["currency"] == "USD"
        assert data["saldo"] == "150.50"
        assert isinstance(data["wallet_id"], str)

        business = Business.objects.get(user=api_client.user)
        wallet = business.wallet
        assert wallet.tipo == "business"
        assert wallet.currency == "USD"
        assert wallet.saldo == Decimal("150.50")
        assert wallet.business_id == business.pk
        # El capital inicial quedó auditado (ADR-08: BalanceAuditLog).
        assert wallet.audit_logs.filter(reason="capital_inicial").exists()

    def test_creates_with_zero_capital(self, api_client) -> None:
        data = _create_business(api_client)
        assert data["saldo"] == "0.00"

    def test_get_returns_profile(self, api_client) -> None:
        created = _create_business(api_client, initial_capital="25.00")
        resp = api_client.get("/api/business")
        assert resp.status_code == 200
        assert resp.data == created

    def test_get_404_without_business(self, api_client) -> None:
        resp = api_client.get("/api/business")
        assert resp.status_code == 404

    def test_duplicate_rejected_409(self, api_client) -> None:
        _create_business(api_client)
        resp = api_client.post("/api/business", {"name": "Otro", "currency": "USD"})
        assert resp.status_code == 409

    def test_empty_name_rejected(self, api_client) -> None:
        resp = api_client.post("/api/business", {"name": "   ", "currency": "USD"})
        assert resp.status_code == 400

    def test_negative_capital_rejected(self, api_client) -> None:
        resp = api_client.post(
            "/api/business",
            {"name": "Negocio", "currency": "USD", "initial_capital": "-5.00"},
        )
        assert resp.status_code == 400

    def test_business_wallet_cannot_be_created_via_wallets_crud(self, api_client) -> None:
        resp = api_client.post(
            "/api/wallets", {"name": "Fondo", "currency": "USD", "tipo": "business"}
        )
        assert resp.status_code == 400


@pytest.mark.django_db
class TestBusinessSummary:
    """GET /api/business/summary agrega SOLO la cuenta del negocio."""

    def test_reports_saldo_and_monthly_totals(self, api_client) -> None:
        _create_business(api_client, initial_capital="100.00")
        wallet = _business_wallet(api_client)
        today = date.today()
        # Cobro y pago pagados dentro del mes actual sobre la cuenta del negocio.
        TransactionFactory(
            user=api_client.user, wallet=wallet, tipo="cobro", estado="pagado",
            monto=Decimal("40.00"), moneda="USD", monto_usd=Decimal("40.00"),
            fecha_pagado=timezone.now(), fecha=today,
        )
        TransactionFactory(
            user=api_client.user, wallet=wallet, tipo="pago", estado="pagado",
            monto=Decimal("15.00"), moneda="USD", monto_usd=Decimal("15.00"),
            fecha_pagado=timezone.now(), fecha=today,
        )
        resp = api_client.get("/api/business/summary")
        assert resp.status_code == 200
        assert resp.data["saldo"] == "100.00"
        assert resp.data["ingresos_mes"] == "40.00"
        assert resp.data["egresos_mes"] == "15.00"

    def test_excludes_pending_and_other_user(self, api_client, auth_client_factory) -> None:
        _create_business(api_client, initial_capital="0.00")
        wallet = _business_wallet(api_client)
        # Pendiente: no cuenta en los totales del mes.
        TransactionFactory(
            user=api_client.user, wallet=wallet, tipo="cobro", estado="pendiente",
            monto=Decimal("50.00"), moneda="USD", monto_usd=Decimal("50.00"),
        )
        # Operaciones pagadas de OTRO usuario: jamás entran en este resumen.
        other_client = auth_client_factory()
        _create_business(other_client, name="Otro Negocio", initial_capital="0.00")
        other_wallet = _business_wallet(other_client)
        TransactionFactory(
            user=other_client.user, wallet=other_wallet, tipo="cobro", estado="pagado",
            monto=Decimal("999.00"), moneda="USD", monto_usd=Decimal("999.00"),
            fecha_pagado=timezone.now(),
        )
        resp = api_client.get("/api/business/summary")
        assert resp.status_code == 200
        assert resp.data["ingresos_mes"] == "0.00"
        assert resp.data["egresos_mes"] == "0.00"
        assert resp.data["recent"] == []

    def test_404_without_business(self, api_client) -> None:
        resp = api_client.get("/api/business/summary")
        assert resp.status_code == 404


@pytest.mark.django_db
class TestSegregation:
    """Los mundos personal y negocio nunca se mezclan."""

    def _seed_both_worlds(self, api_client):
        """Usuario con una wallet personal y un negocio, cada uno con operaciones."""
        _create_business(api_client, initial_capital="100.00")
        business_wallet = _business_wallet(api_client)
        personal_wallet = WalletFactory(user=api_client.user, saldo=Decimal("10.00"), currency="USD")

        TransactionFactory(
            user=api_client.user, wallet=business_wallet, tipo="cobro", estado="pagado",
            monto=Decimal("80.00"), moneda="USD", monto_usd=Decimal("80.00"),
            fecha_pagado=timezone.now(), concepto="Venta del negocio",
        )
        TransactionFactory(
            user=api_client.user, wallet=personal_wallet, tipo="pago", estado="pagado",
            monto=Decimal("30.00"), moneda="USD", monto_usd=Decimal("30.00"),
            fecha_pagado=timezone.now(), concepto="Compra personal",
        )
        return business_wallet, personal_wallet

    def test_wallets_list_default_is_private_only(self, api_client) -> None:
        _, personal_wallet = self._seed_both_worlds(api_client)
        resp = api_client.get("/api/wallets")
        ids = {row["id"] for row in resp.data["results"]}
        assert ids == {str(personal_wallet.pk)}
        # Y el scope business expone solo la del negocio.
        bresp = api_client.get("/api/wallets?scope=business")
        assert len(bresp.data["results"]) == 1
        assert bresp.data["results"][0]["tipo"] == "business"

    def test_transactions_list_default_is_private_only(self, api_client) -> None:
        _, personal_wallet = self._seed_both_worlds(api_client)
        resp = api_client.get("/api/transactions")
        concepts = {row["concepto"] for row in resp.data["results"]}
        assert concepts == {"Compra personal"}

        bresp = api_client.get("/api/transactions?scope=business")
        concepts_biz = {row["concepto"] for row in bresp.data["results"]}
        assert concepts_biz == {"Venta del negocio"}

    def test_transactions_cannot_cross_scope_via_wallet_filter(self, api_client) -> None:
        business_wallet, _ = self._seed_both_worlds(api_client)
        # Filtrando por la wallet del negocio en scope personal: vacío.
        resp = api_client.get(f"/api/transactions?scope=personal&wallet={business_wallet.pk}")
        assert resp.data["results"] == []

    def test_overview_excludes_business_wallet_and_operations(self, api_client) -> None:
        self._seed_both_worlds(api_client)
        resp = api_client.get("/api/overview")
        assert resp.status_code == 200
        # El saldo del negocio (100) NO suma al total personal (10 USD).
        assert resp.data["total_balance_usd"] == "10.00"
        assert len(resp.data["wallets"]) == 1
        # El cobro del negocio NO cuenta en "collected_month".
        assert resp.data["collected_month"] == "0.00"

    def test_transfer_business_to_personal_rejected(self, api_client) -> None:
        business_wallet, personal_wallet = self._seed_both_worlds(api_client)
        with pytest.raises(BusinessRuleError):
            create_transfer(business_wallet, personal_wallet, Decimal("10.00"))

    def test_transfer_personal_to_business_rejected(self, api_client) -> None:
        business_wallet, personal_wallet = self._seed_both_worlds(api_client)
        with pytest.raises(BusinessRuleError):
            create_transfer(personal_wallet, business_wallet, Decimal("10.00"))

    def test_personal_to_personal_transfer_still_works(self, api_client) -> None:
        self._seed_both_worlds(api_client)
        WalletFactory(user=api_client.user, saldo=Decimal("5.00"), currency="USD")
        w_a = Wallet.objects.filter(user=api_client.user, business__isnull=True).first()
        w_b = Wallet.objects.filter(user=api_client.user, business__isnull=True).exclude(pk=w_a.pk).first()
        assert w_a is not None and w_b is not None
        tx = create_transfer(w_a, w_b, Decimal("2.00"))
        assert tx.tipo == "transferencia"
        assert Transaction.objects.filter(pk=tx.pk, wallet__business__isnull=True).exists()

    def test_other_users_business_is_invisible(self, api_client, auth_client_factory) -> None:
        other_client = auth_client_factory()
        _create_business(other_client, name="Ajeno", initial_capital="500.00")
        resp = api_client.get("/api/business")
        assert resp.status_code == 404
        assert api_client.get("/api/wallets?scope=business").data["results"] == []
        assert api_client.get("/api/transactions?scope=business").data["results"] == []