"""tests — CRUD de billeteras y ajuste manual de saldo."""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.wallets.services import adjust_balance
from factories import UserFactory, WalletFactory


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