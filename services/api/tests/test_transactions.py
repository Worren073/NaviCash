"""tests — Operaciones: CRUD, transiciones de estado y efectos en billetera.

Cubre las reglas de negocio del núcleo (ADR-08):
- Crear operación pagada ajusta el saldo (cobro suma, pago resta).
- Cancelar/revocar revierte el efecto.
- "retrasado" es derivado y se filtra por API.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.db import IntegrityError, connection
from django.utils import timezone

from apps.transactions.models import Transaction
from apps.transactions.services import mark_paid, set_state
from factories import ContactFactory, TransactionFactory, WalletFactory


@pytest.mark.django_db
class TestTransactionCreate:
    """POST /api/transactions."""

    URL = "/api/transactions"

    def _payload(self, **overrides) -> dict:
        base = {
            "tipo": "pago",
            "monto": "50.00",
            "moneda": "USD",
            "concepto": "Servicio",
            "estado": "pendiente",
        }
        base.update(overrides)
        return base

    def test_creates_pending_with_usd_frozen(self, api_client) -> None:
        """Una operación en USD congela monto_usd = monto y tasa = 1."""
        resp = api_client.post(self.URL, self._payload())
        assert resp.status_code == 201
        body = resp.data
        assert body["estado"] == "pendiente"
        assert body["monto_usd"] == "50.00"
        assert body["tasa_usd"] == "1.0000"

    def test_creates_paid_applies_to_wallet(self, api_client) -> None:
        """Crear un pago pagado descuenta la billetera (USD)."""
        wallet = WalletFactory(user=api_client.user, saldo=Decimal("100.00"))
        resp = api_client.post(
            self.URL, self._payload(estado="pagado", wallet=str(wallet.id))
        )
        assert resp.status_code == 201
        wallet.refresh_from_db()
        assert wallet.saldo == Decimal("50.00")

    def test_create_cobro_pagado_sums_to_wallet(self, api_client) -> None:
        """Crear un cobro pagado suma a la billetera."""
        wallet = WalletFactory(user=api_client.user, saldo=Decimal("0.00"))
        resp = api_client.post(
            self.URL,
            self._payload(tipo="cobro", estado="pagado", wallet=str(wallet.id)),
        )
        assert resp.status_code == 201
        wallet.refresh_from_db()
        assert wallet.saldo == Decimal("50.00")

    def test_rejects_wallet_in_different_currency(self, api_client) -> None:
        """Una billetera VES no admite operación USD."""
        wallet = WalletFactory(user=api_client.user, currency="VES")
        resp = api_client.post(
            self.URL, self._payload(moneda="USD", wallet=str(wallet.id))
        )
        assert resp.status_code == 400

    def test_rejects_negative_monto(self, api_client) -> None:
        """Montos <= 0 son rechazados."""
        resp = api_client.post(self.URL, self._payload(monto="-5.00"))
        assert resp.status_code == 400

    def test_rejects_other_users_wallet(self, auth_client_factory) -> None:
        """No se puede usar una billetera de otro usuario."""
        other_wallet = WalletFactory()
        client = auth_client_factory()
        resp = client.post(
            self.URL,
            self._payload(wallet=str(other_wallet.id)),
        )
        assert resp.status_code in (400, 404)


@pytest.mark.django_db
class TestStateTransition:
    """POST /api/transactions/<id>/state."""

    def test_mark_paid_effect(self, api_client) -> None:
        """Marcar pagado un pago pendiente descuenta la billetera."""
        wallet = WalletFactory(user=api_client.user, saldo=Decimal("100.00"))
        tx = TransactionFactory(
            user=api_client.user, wallet=wallet, tipo="pago", monto=Decimal("30.00")
        )
        resp = api_client.post(f"/api/transactions/{tx.id}/state", {"estado": "pagado"})
        assert resp.status_code == 200
        wallet.refresh_from_db()
        assert wallet.saldo == Decimal("70.00")

    def test_cancel_paid_reverts_wallet(self, api_client) -> None:
        """Cancelar una operación pagada revierte el saldo."""
        wallet = WalletFactory(user=api_client.user, saldo=Decimal("100.00"))
        tx = TransactionFactory(
            user=api_client.user, wallet=wallet, tipo="pago", monto=Decimal("30.00")
        )
        mark_paid(tx)
        resp = api_client.post(f"/api/transactions/{tx.id}/state", {"estado": "cancelado"})
        assert resp.status_code == 200
        wallet.refresh_from_db()
        assert wallet.saldo == Decimal("100.00")

    def test_already_paid_rejected(self, api_client) -> None:
        """Intentar pagar una operación ya pagada da error 400."""
        tx = TransactionFactory(user=api_client.user, estado="pagado")
        resp = api_client.post(f"/api/transactions/{tx.id}/state", {"estado": "pagado"})
        assert resp.status_code == 400


@pytest.mark.django_db
class TestOverdue:
    """Filtro del estado derivado 'retrasado'."""

    def test_overdue_detected_in_list(self, api_client) -> None:
        """Una operación vencida y pendiente aparece con estado retrasado."""
        tx = TransactionFactory(
            user=api_client.user,
            estado="pendiente",
            fecha=date.today() - timedelta(days=5),
            fecha_vencimiento=date.today() - timedelta(days=1),
        )
        resp = api_client.get("/api/transactions")
        assert resp.status_code == 200
        items = resp.data["results"]
        assert len(items) == 1
        assert items[0]["effective_state"] == "retrasado"
        assert items[0]["is_overdue"] is True

    def test_filter_by_retrasado(self, api_client) -> None:
        """?estado=retrasado solo devuelve las vencidas."""
        TransactionFactory(
            user=api_client.user,
            estado="pendiente",
            fecha=date.today() - timedelta(days=5),
            fecha_vencimiento=date.today() - timedelta(days=1),
        )
        TransactionFactory(
            user=api_client.user,
            estado="pendiente",
            fecha_vencimiento=date.today() + timedelta(days=1),
        )
        resp = api_client.get("/api/transactions?estado=retrasado")
        items = resp.data["results"]
        assert len(items) == 1
        assert items[0]["effective_state"] == "retrasado"


@pytest.mark.django_db
class TestContactsAndCategories:
    """Endpoints auxiliares: /api/contacts y /api/categories."""

    def test_create_contact(self, api_client) -> None:
        """Crear un contacto."""
        resp = api_client.post("/api/contacts", {"name": "María", "note": "Colega"})
        assert resp.status_code == 201
        assert resp.data["name"] == "María"

    def test_default_categories_created_on_register(self) -> None:
        """El registro crea las categorías por defecto (señal de bootstrap)."""
        from apps.transactions.models import Category
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.create_user("cat@example.com", "clave-segura")
        assert Category.objects.filter(user=user).count() >= 10

    def test_transaction_with_contact(self, api_client) -> None:
        """Crear una operación con contacto y categoría."""
        contact = ContactFactory(user=api_client.user)
        resp = api_client.post(
            "/api/transactions",
            {
                "tipo": "pago",
                "monto": "10.00",
                "moneda": "USD",
                "contact": str(contact.id),
            },
        )
        assert resp.status_code == 201
        assert resp.data["contact"] == contact.id


def _check_constraints_supported() -> None:
    """CheckConstraint solo se prueba si el motor las ejecuta (A10).

    SQLite (test_settings) y PostgreSQL las soportan; se omite con razón
    explícita en motores sin soporte de tablas (ej. SQLite muy viejo).
    """
    if not connection.features.supports_table_check_constraints:
        pytest.skip(
            "El motor no soporta CheckConstraints a nivel de tabla; "
            "la constraint se aplica solo en motores que las ejecutan."
        )


@pytest.mark.django_db
class TestSoftDelete:
    """C4: borrar una operación la oculta de la API pero no borra historial."""

    URL = "/api/transactions"

    def test_deleted_hidden_from_list_but_stays_in_db(self, api_client) -> None:
        """DELETE oculta la operación del listado; sigue en BD (all_objects)."""
        tx = TransactionFactory(
            user=api_client.user, tipo="pago", monto=Decimal("30.00")
        )
        resp = api_client.delete(f"{self.URL}/{tx.id}")
        assert resp.status_code == 204
        # Oculto de la API pública...
        listing = api_client.get(self.URL)
        assert listing.data["count"] == 0
        assert Transaction.objects.filter(pk=tx.id).count() == 0
        # ...pero el historial persiste marcado como borrado.
        archived = Transaction.all_objects.get(pk=tx.id)
        assert archived.is_deleted is True

    def test_delete_paid_reverses_wallet_then_hides(self, api_client) -> None:
        """Borrar una operación pagada sigue revirtiendo la billetera (R9)."""
        wallet = WalletFactory(user=api_client.user, saldo=Decimal("100.00"))
        tx = TransactionFactory(
            user=api_client.user, wallet=wallet, tipo="pago", monto=Decimal("30.00")
        )
        mark_paid(tx)
        api_client.delete(f"{self.URL}/{tx.id}")
        wallet.refresh_from_db()
        assert wallet.saldo == Decimal("100.00")
        assert Transaction.objects.filter(pk=tx.id).count() == 0
        assert Transaction.all_objects.get(pk=tx.id).is_deleted is True

    def test_deleted_tx_not_reachable_by_endpoint(self, api_client) -> None:
        """Tras el borrado, el detalle/estado responden 404 (scoping de borrado)."""
        tx = TransactionFactory(user=api_client.user)
        api_client.delete(f"{self.URL}/{tx.id}")
        resp = api_client.get(f"{self.URL}/{tx.id}")
        assert resp.status_code == 404
        resp = api_client.post(f"{self.URL}/{tx.id}/state", {"estado": "pagado"})
        assert resp.status_code == 404

    def test_soft_delete_does_not_touch_other_users(self, auth_client_factory) -> None:
        """Un borrado de otro usuario responde 404 y no marca nada."""
        tx = TransactionFactory()
        client = auth_client_factory()
        assert client.delete(f"{self.URL}/{tx.id}").status_code == 404
        assert Transaction.all_objects.get(pk=tx.id).is_deleted is False


@pytest.mark.django_db
class TestCheckConstraints:
    """A10: el motor rechaza datos inválidos aunque la API no los vea.

    Se inserta con ``Transaction.objects.create`` (saltándose serializers) para
    probar la constraint a nivel de BD.
    """

    def test_monto_zero_rejected_by_db(self, api_client) -> None:
        """monto <= 0 lanza IntegrityError en el motor."""
        _check_constraints_supported()
        with pytest.raises(IntegrityError):
            Transaction.objects.create(
                user=api_client.user,
                tipo="pago",
                monto=Decimal("0.00"),
                moneda="USD",
            )

    def test_monto_negative_rejected_by_db(self, api_client) -> None:
        """monto negativo lanza IntegrityError en el motor."""
        _check_constraints_supported()
        with pytest.raises(IntegrityError):
            Transaction.objects.create(
                user=api_client.user,
                tipo="cobro",
                monto=Decimal("-5.00"),
                moneda="USD",
            )

    def test_vencimiento_before_fecha_rejected_by_db(self, api_client) -> None:
        """fecha_vencimiento < fecha lanza IntegrityError en el motor."""
        _check_constraints_supported()
        with pytest.raises(IntegrityError):
            Transaction.objects.create(
                user=api_client.user,
                tipo="pago",
                monto=Decimal("10.00"),
                moneda="USD",
                fecha=date.today(),
                fecha_vencimiento=date.today() - timedelta(days=1),
            )

    def test_vencimiento_null_allowed(self, api_client) -> None:
        """Sin vencimiento la fila es válida (condición IS NULL OR ...)."""
        _check_constraints_supported()
        tx = Transaction.objects.create(
            user=api_client.user, tipo="pago", monto=Decimal("10.00"), moneda="USD"
        )
        assert tx.pk is not None

    def test_valid_monto_still_creates(self, api_client) -> None:
        """Un monto válido sigue creándose (la constraint no bloquea lo lícito)."""
        tx = Transaction.objects.create(
            user=api_client.user,
            tipo="pago",
            monto=Decimal("10.00"),
            moneda="USD",
            estado="pagado",
            fecha_pagado=timezone.now(),
        )
        assert tx.pk is not None