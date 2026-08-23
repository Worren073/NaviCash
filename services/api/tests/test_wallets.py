"""tests — CRUD de billeteras y ajuste manual de saldo."""

from __future__ import annotations

import threading
from decimal import Decimal

import pytest
from django.db import IntegrityError, connection

from apps.transactions.models import Transaction
from apps.transactions.services import mark_paid
from apps.wallets.models import BalanceAuditLog, Wallet
from apps.wallets.services import adjust_balance
from factories import ExchangeRateFactory, TransactionFactory, UserFactory, WalletFactory


def _require_row_lock() -> None:
    """SQLite (test_settings por defecto) no ejecuta ``SELECT ... FOR UPDATE``.

    El bloqueo real de filas solo existe en PostgreSQL: con SQLite el
    ``select_for_update`` de Django es un no-op y el test de concurrencia
    sería un falso positivo/flaky, así que se omite con una razón explícita
    y se ejecuta cuando la suite corre contra el Postgres del contenedor
    (ej: ``DJANGO_SETTINGS_MODULE=config.settings``).
    """
    if connection.vendor != "postgresql":
        pytest.skip(
            "select_for_update es un no-op en SQLite; ejecuta la suite con "
            "DJANGO_SETTINGS_MODULE=config.settings contra PostgreSQL."
        )


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

    def test_nan_delta_rejected(self, api_client) -> None:
        """NaN no se acepta como delta: 400 en vez de corromper el saldo."""
        wallet = WalletFactory(user=api_client.user, saldo=Decimal("10.00"))
        resp = api_client.post(f"/api/wallets/{wallet.id}/adjust", {"delta": "NaN"})
        assert resp.status_code == 400
        wallet.refresh_from_db()
        assert wallet.saldo == Decimal("10.00")

    def test_infinity_new_balance_rejected(self, api_client) -> None:
        """Infinity no se acepta como new_balance: 400."""
        wallet = WalletFactory(user=api_client.user, saldo=Decimal("10.00"))
        resp = api_client.post(f"/api/wallets/{wallet.id}/adjust", {"new_balance": "Infinity"})
        assert resp.status_code == 400
        wallet.refresh_from_db()
        assert wallet.saldo == Decimal("10.00")


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


@pytest.mark.django_db(transaction=True)
class TestAdjustBalanceConcurrency:
    """Concurrencia REAL (hallazgo C1): dos hilos ajustan la misma billetera.

    ``threading.Barrier`` dispara ambos hilos a la vez y ``transaction=True``
    desactiva el runner de transacciones anidadas: cada hilo abre su propia
    transacción real contra la BD. El ``select_for_update`` de ``adjust_balance``
    serializa ambas operaciones a nivel de fila; el test es determinista.
    """

    def _run_concurrent(self, wallet, deltas):
        """Lanza un hilo por delta y espera a todos con timeout."""
        barrier = threading.Barrier(len(deltas))
        errors = []

        def worker(delta):
            barrier.wait()
            try:
                adjust_balance(wallet, delta)
            except ValueError as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(d,)) for d in deltas]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        assert not any(t.is_alive() for t in threads), "Hilos colgados en adjust_balance"
        return errors

    def test_two_positive_deltas_no_lost_update(self) -> None:
        """Dos sumas simultáneas de 25.00 sobre 100.00: saldo final 150.00.

        Sin bloqueo de fila ambos hilos leerían 100.00 y el último write
        ganaría (125.00 -> pérdida de actualización); con el lock el saldo
        es la suma exacta.
        """
        _require_row_lock()
        wallet = WalletFactory(user=UserFactory(), saldo=Decimal("100.00"))
        errors = self._run_concurrent(wallet, [Decimal("25.00"), Decimal("25.00")])
        assert errors == []
        wallet.refresh_from_db()
        assert wallet.saldo == Decimal("150.00")

    def test_overspend_raises_exactly_once(self) -> None:
        """Dos giros simultáneos de 60.00 sobre 100.00: solo uno prospera.

        Ambos hilos parten de 100.00; el primero deja 40.00 y el segundo,
        que re-lee la fila bloqueada tras el commit del primero, ve 40.00 y
        lanza ``ValueError``. El saldo final es 40.00: sin sobregiro ni
        doble gasto (validación < 0 tras el lock).
        """
        _require_row_lock()
        wallet = WalletFactory(user=UserFactory(), saldo=Decimal("100.00"))
        errors = self._run_concurrent(wallet, [Decimal("-60.00"), Decimal("-60.00")])
        assert len(errors) == 1
        wallet.refresh_from_db()
        assert wallet.saldo == Decimal("40.00")


@pytest.mark.django_db
class TestBalanceAuditLog:
    """C4: cada ajuste de saldo deja una pista de auditoría (misma transacción)."""

    def test_audit_log_created_on_payment(self, api_client) -> None:
        """Marcar un pago pagado crea el log con delta, saldo y motivo."""
        wallet = WalletFactory(user=api_client.user, saldo=Decimal("100.00"))
        tx = TransactionFactory(
            user=api_client.user, wallet=wallet, tipo="pago", monto=Decimal("30.00")
        )
        mark_paid(tx)
        log = BalanceAuditLog.objects.get(wallet=wallet)
        assert log.delta == Decimal("-30.00")
        assert log.balance_after == Decimal("70.00")
        assert log.reason == f"transaction-{tx.pk}"
        assert log.user_id == api_client.user.id
        assert log.created_at is not None

    def test_audit_log_created_on_wallet_adjust(self, api_client) -> None:
        """El ajuste manual (POST /adjust) también audita con su motivo."""
        wallet = WalletFactory(user=api_client.user, saldo=Decimal("5.00"))
        resp = api_client.post(f"/api/wallets/{wallet.id}/adjust", {"delta": "20.00"})
        assert resp.status_code == 200
        log = BalanceAuditLog.objects.get(wallet=wallet)
        assert log.delta == Decimal("20.00")
        assert log.balance_after == Decimal("25.00")
        assert log.reason == "ajuste_manual"

    def test_audit_log_created_on_transfer(self, api_client) -> None:
        """Una transferencia audita ambos lados (transfer-out / transfer-in)."""
        a = WalletFactory(user=api_client.user, currency="USD", saldo=Decimal("100.00"))
        b = WalletFactory(user=api_client.user, currency="USD", saldo=Decimal("10.00"))
        resp = api_client.post(
            "/api/wallets/transfer",
            {"source": str(a.id), "target": str(b.id), "amount": "30.00"},
        )
        assert resp.status_code == 201
        reasons = sorted(BalanceAuditLog.objects.values_list("reason", flat=True))
        assert reasons == ["transfer-in", "transfer-out"]
        assert BalanceAuditLog.objects.get(wallet=a).balance_after == Decimal("70.00")
        assert BalanceAuditLog.objects.get(wallet=b).balance_after == Decimal("40.00")

    def test_failed_adjust_leaves_no_audit_log(self, api_client) -> None:
        """Un ajuste rechazado (saldo insuficiente) no escribe log: atómico."""
        wallet = WalletFactory(user=api_client.user, saldo=Decimal("5.00"))
        resp = api_client.post(f"/api/wallets/{wallet.id}/adjust", {"delta": "-10.00"})
        assert resp.status_code == 400
        assert BalanceAuditLog.objects.filter(wallet=wallet).count() == 0


@pytest.mark.django_db
class TestWalletSoftDelete:
    """C4: la destrucción de billeteras es soft, y se bloquea con saldo."""

    URL = "/api/wallets"

    def test_empty_wallet_deleted_is_hidden_from_list(self, api_client) -> None:
        """Borrar una billetera vacía responde 204 y la oculta del listado."""
        wallet = WalletFactory(user=api_client.user, saldo=Decimal("0.00"))
        resp = api_client.delete(f"{self.URL}/{wallet.id}")
        assert resp.status_code == 204
        listing = api_client.get(self.URL)
        assert listing.data["count"] == 0
        assert Wallet.objects.filter(pk=wallet.id).count() == 0
        assert Wallet.all_objects.get(pk=wallet.id).is_deleted is True

    def test_wallet_with_balance_cannot_be_deleted(self, api_client) -> None:
        """Una billetera con saldo no puede ocultarse: 400 y sigue visible."""
        wallet = WalletFactory(user=api_client.user, saldo=Decimal("50.00"))
        resp = api_client.delete(f"{self.URL}/{wallet.id}")
        assert resp.status_code == 400
        assert Wallet.all_objects.get(pk=wallet.id).is_deleted is False
        listing = api_client.get(self.URL)
        assert listing.data["count"] == 1

    def test_hidden_wallet_not_reachable(self, api_client) -> None:
        """Tras ocultar la billetera, su detalle responde 404."""
        wallet = WalletFactory(user=api_client.user)
        api_client.delete(f"{self.URL}/{wallet.id}")
        resp = api_client.get(f"{self.URL}/{wallet.id}")
        assert resp.status_code == 404

    def test_zero_balance_after_adjust_allows_delete(self, api_client) -> None:
        """Al dejar el saldo en 0, la billetera sí puede ocultarse."""
        wallet = WalletFactory(user=api_client.user, saldo=Decimal("10.00"))
        api_client.post(f"{self.URL}/{wallet.id}/adjust", {"delta": "-10.00"})
        resp = api_client.delete(f"{self.URL}/{wallet.id}")
        assert resp.status_code == 204


@pytest.mark.django_db
class TestWalletCheckConstraints:
    """A10: el motor rechaza saldos negativos aunque la API los saltara."""

    def test_negative_saldo_rejected_by_db(self, api_client) -> None:
        """saldo < 0 lanza IntegrityError en el motor."""
        wallet = WalletFactory(user=api_client.user, saldo=Decimal("5.00"))
        with pytest.raises(IntegrityError):
            Wallet.objects.filter(pk=wallet.pk).update(saldo=Decimal("-1.00"))


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

    def test_usd_to_ves_with_euro_rate(self, api_client) -> None:
        """USD→VES con la tasa del euro multiplica por EUR/VES (venta)."""
        us, ves = self._usd_and_ves(api_client)
        resp = api_client.post(
            self.URL,
            {"source": str(us.id), "target": str(ves.id), "amount": "10.00",
             "rate_source": "euro"},
        )
        assert resp.status_code == 201
        us.refresh_from_db(); ves.refresh_from_db()
        # Proveedor estático en tests: euro = 100 * 1.1 = 110 VES/EUR.
        assert us.saldo == Decimal("90.00")
        assert ves.saldo == Decimal("1100.00")
        body = resp.data["transfer"]
        assert body["tasa_fuente"] == "euro"
        assert Decimal(body["monto_destino"]) == Decimal("1100.00")

    def test_ves_to_usd_with_euro_rate(self, api_client) -> None:
        """VES→USD con la tasa del euro divide (compra)."""
        us, ves = self._usd_and_ves(api_client, usd_balance="0.00", ves_balance="2200.00")
        resp = api_client.post(
            self.URL,
            {"source": str(ves.id), "target": str(us.id), "amount": "2200.00",
             "rate_source": "euro"},
        )
        assert resp.status_code == 201
        us.refresh_from_db(); ves.refresh_from_db()
        assert ves.saldo == Decimal("0.00")
        # 2200 / 110 (tasa euro estática) = 20 USD.
        assert us.saldo == Decimal("20.00")

    def test_rejects_invalid_rate_source(self, api_client) -> None:
        """Un rate_source desconocido responde 400."""
        us, ves = self._usd_and_ves(api_client)
        resp = api_client.post(
            self.URL,
            {"source": str(us.id), "target": str(ves.id), "amount": "5.00",
             "rate_source": "paralelo"},
        )
        assert resp.status_code == 400

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