"""tests — CRUD de billeteras y ajuste manual de saldo."""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.transactions.models import Transaction
from apps.wallets.services import adjust_balance
from factories import ExchangeRateFactory, UserFactory, WalletFactory


@pytest.mark.django_db
class TestWalletCreate:
    """POST /api/wallets."""

    URL = "/api/wallets"

    def test_creates_with_initial_balance(self, api_client) -> None:
        """Crea una billetera con su saldo inicial."""
        resp = api_client.post(
            self.URL, {"name": "Efectivo", "currency": "USD", "saldo_inicial": "100.00"}
        )
        assert resp.status_code == 201
        assert resp.data["saldo"] == "100.00"

    def test_creates_with_zero_balance_by_default(self, api_client) -> None:
        """Sin saldo inicial se crea con 0.00."""
        resp = api_client.post(self.URL, {"name": "Banco", "currency": "VES"})
        assert resp.status_code == 201
        assert resp.data["saldo"] == "0.00"


@pytest.mark.django_db
class TestWalletAdjust:
    """POST /api/wallets/<id>/adjust (ajuste manual ADR-08)."""

    def test_delta_increases(self, api_client) -> None:
        """Añadir saldo a una billetera USD eleva el saldo."""
        wallet = WalletFactory(user=api_client.user)
        resp = api_client.post(f"/api/wallets/{wallet.id}/adjust", {"delta": "25.00"})
        assert resp.status_code == 200
        wallet.refresh_from_db()
        assert wallet.saldo == Decimal("25.00")

    def test_new_balance_sets_absolute(self, api_client) -> None:
        """new_balance fija el saldo absoluto."""
        wallet = WalletFactory(user=api_client.user, saldo=Decimal("50.00"))
        resp = api_client.post(f"/api/wallets/{wallet.id}/adjust", {"new_balance": "10.00"})
        assert resp.status_code == 200
        wallet.refresh_from_db()
        assert wallet.saldo == Decimal("10.00")

    def test_negative_balance_rejected(self, api_client) -> None:
        """No se permite dejar la billetera en negativo."""
        wallet = WalletFactory(user=api_client.user, saldo=Decimal("5.00"))
        resp = api_client.post(f"/api/wallets/{wallet.id}/adjust", {"delta": "-10.00"})
        assert resp.status_code == 400

    def test_missing_parameter_rejected(self, api_client) -> None:
        """Faltando delta/new_balance responde 400."""
        wallet = WalletFactory(user=api_client.user)
        resp = api_client.post(f"/api/wallets/{wallet.id}/adjust", {})
        assert resp.status_code == 400


@pytest.mark.django_db
class TestAdjustBalanceService:
    """Testeo directo del servicio de negocio."""

    def test_rejects_negative_result(self) -> None:
        """adjust_balance lanza ValueError si el saldo quedaría negativo."""
        user = UserFactory()
        wallet = WalletFactory(user=user, saldo=Decimal("1.00"))
        with pytest.raises(ValueError):
            adjust_balance(wallet, Decimal("-2.00"))

    def test_accepts_reason_and_updates(self) -> None:
        """Un ajuste positivo actualiza el saldo y con razón opcional."""
        user = UserFactory()
        wallet = WalletFactory(user=user, saldo=Decimal("0.00"))
        result = adjust_balance(wallet, Decimal("100"), reason="test")
        assert result == Decimal("100.00")
        wallet.refresh_from_db()
        assert wallet.saldo == Decimal("100.00")


@pytest.mark.django_db
class TestOwnerScoping:
    """Un usuario no debe leer ni mutar billeteras de otro."""

    def test_list_only_own(self, auth_client_factory) -> None:
        """El listado solo devuelve las billeteras del usuario autenticado."""
        other = UserFactory()
        WalletFactory(user=other, name="Ajena")  # billetera de otro usuario
        client = auth_client_factory()
        resp = client.get("/api/wallets")
        assert resp.status_code == 200
        assert resp.data["count"] == 0

    def test_cannot_adjust_other_wallet(self, auth_client_factory) -> None:
        """Un usuario no puede ajustar la billetera de otro."""
        other = UserFactory()
        wallet = WalletFactory(user=other)
        client = auth_client_factory()
        resp = client.post(f"/api/wallets/{wallet.id}/adjust", {"delta": "1.00"})
        assert resp.status_code in (404, 403)


@pytest.mark.django_db
class TestWalletTransfer:
    """POST /api/wallets/transfer (transferencia entre cuentas)."""

    URL = "/api/wallets/transfer"

    def _usd_and_ves(self, api_client, usd_balance: str = "100.00", ves_balance: str = "0.00"):
        """Crea dos billeteras (USD y VES) para el usuario."""
        usd = WalletFactory(user=api_client.user, name="Efectivo USD", currency="USD", saldo=Decimal(usd_balance))
        ves = WalletFactory(user=api_client.user, name="Efectivo VES", currency="VES", saldo=Decimal(ves_balance))
        return usd, ves

    def test_same_currency_moves_balances(self, api_client) -> None:
        """Transferencia USD→USD mueve el monto y crea operación tipo transferencia."""
        a = WalletFactory(user=api_client.user, currency="USD", saldo=Decimal("100.00"))
        b = WalletFactory(user=api_client.user, currency="USD", saldo=Decimal("10.00"))
        resp = api_client.post(self.URL, {"source": str(a.id), "target": str(b.id), "amount": "30.00"})
        assert resp.status_code == 201
        a.refresh_from_db(); b.refresh_from_db()
        assert a.saldo == Decimal("70.00")
        assert b.saldo == Decimal("40.00")
        tx = Transaction.objects.filter(user=api_client.user, tipo="transferencia").first()
        assert tx is not None
        assert tx.dest_wallet_id == b.id
        assert tx.monto_destino == Decimal("30.00")
        assert tx.estado == "pagado"

    def test_usd_to_ves_uses_rate_manual(self, api_client) -> None:
        """USD→VES con tasa manual multiplica (venta)."""
        us, ves = self._usd_and_ves(api_client)
        resp = api_client.post(
            self.URL,
            {"source": str(us.id), "target": str(ves.id), "amount": "10.00",
             "rate_source": "manual", "custom_rate": "880.00"},
        )
        assert resp.status_code == 201
        us.refresh_from_db(); ves.refresh_from_db()
        assert us.saldo == Decimal("90.00")
        assert ves.saldo == Decimal("8800.00")
        body = resp.data["transfer"]
        assert body["moneda_destino"] == "VES"
        assert body["monto_destino"] == "8800.00"

    def test_ves_to_usd_uses_buy_unofficial_rate(self, api_client) -> None:
        """VES→USD con tasa oficial divide (compra)."""
        ExchangeRateFactory()
        us, ves = self._usd_and_ves(api_client, usd_balance="0.00", ves_balance="8600.00")
        resp = api_client.post(
            self.URL,
            {"source": str(ves.id), "target": str(us.id), "amount": "8600.00",
             "rate_source": "oficial"},
        )
        assert resp.status_code == 201
        us.refresh_from_db(); ves.refresh_from_db()
        # factory: promedio = 100 → 8600 / 100 = 86
        assert ves.saldo == Decimal("0.00")
        assert us.saldo == Decimal("86.00")

    def test_rejects_insufficient_balance(self, api_client) -> None:
        """Saldo insuficiente en origen responde 400 sin tocar destino."""
        us, ves = self._usd_and_ves(api_client, usd_balance="5.00")
        resp = api_client.post(self.URL, {"source": str(us.id), "target": str(ves.id), "amount": "20.00"})
        assert resp.status_code == 400
        us.refresh_from_db(); ves.refresh_from_db()
        assert us.saldo == Decimal("5.00")
        assert ves.saldo == Decimal("0.00")

    def test_rejects_same_wallet(self, api_client) -> None:
        """No se permite transferir a la misma billetera."""
        us, _ = self._usd_and_ves(api_client)
        resp = api_client.post(self.URL, {"source": str(us.id), "target": str(us.id), "amount": "5.00"})
        assert resp.status_code == 400

    def test_rejects_missing_custom_rate(self, api_client) -> None:
        """Tasa manual sin custom_rate responde 400."""
        us, ves = self._usd_and_ves(api_client)
        resp = api_client.post(
            self.URL,
            {"source": str(us.id), "target": str(ves.id), "amount": "5.00", "rate_source": "manual"},
        )
        assert resp.status_code == 400

    def test_rejects_wallet_from_other_user(self, auth_client_factory) -> None:
        """No se puede transferir con una billetera de otro usuario."""
        other_wallet = WalletFactory(user=UserFactory(), currency="USD", saldo=Decimal("50.00"))
        client = auth_client_factory()
        mine = WalletFactory(user=client.user, currency="USD", saldo=Decimal("50.00"))
        resp = client.post(
            self.URL, {"source": str(mine.id), "target": str(other_wallet.id), "amount": "5.00"}
        )
        assert resp.status_code == 400

    def test_transfer_cannot_be_deleted(self, api_client) -> None:
        """Una transferencia no se puede borrar (inmutable)."""
        us, ves = self._usd_and_ves(api_client)
        resp = api_client.post(
            self.URL,
            {"source": str(us.id), "target": str(ves.id), "amount": "10.00",
             "rate_source": "manual", "custom_rate": "880.00"},
        )
        assert resp.status_code == 201
        tx_id = resp.data["transfer"]["id"]
        del_resp = api_client.delete(f"/api/transactions/{tx_id}")
        assert del_resp.status_code == 400

    def test_transfer_cannot_change_state(self, api_client) -> None:
        """Una transferencia no admite cambios de estado."""
        us, ves = self._usd_and_ves(api_client)
        resp = api_client.post(
            self.URL,
            {"source": str(us.id), "target": str(ves.id), "amount": "10.00",
             "rate_source": "manual", "custom_rate": "880.00"},
        )
        tx_id = resp.data["transfer"]["id"]
        state_resp = api_client.post(f"/api/transactions/{tx_id}/state", {"estado": "cancelado"})
        assert state_resp.status_code == 400