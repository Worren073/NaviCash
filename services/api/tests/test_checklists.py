"""tests — Listas de compras del mercado (checklists).

Cubre: CRUD con ítems anidados (subtotales y total estimado), el cierre con
pago desde una cuenta (egreso + descuento atómico), reglas de negocio (una
sola completación, cuenta propia y de la misma moneda, saldo suficiente,
inmutabilidad tras completar), owner-scoping, CheckConstraints del motor y la
concurrencia real de dos completaciones simultáneas.
"""

from __future__ import annotations

import threading
from decimal import Decimal

import pytest
from django.db import IntegrityError, connection
from rest_framework.test import APIClient

from apps.checklists.models import ListItem, ShoppingList
from apps.transactions.models import Transaction
from apps.wallets.models import BalanceAuditLog
from factories import ExchangeRateFactory, UserFactory, WalletFactory


URL = "/api/checklists"


def _list_payload(**overrides) -> dict:
    """Payload válido de una lista con un producto sin marcar."""
    payload = {
        "name": "Mercado de la semana",
        "currency": "USD",
        "items": [{"name": "Harina", "precio_unitario": "2.50", "cantidad": 2}],
    }
    payload.update(overrides)
    return payload


def _add_checked_item(shopping_list, *, user, name="Harina", price="2.50", cantidad=2):
    """Crea un producto marcado con precio y cantidad válidos (completable)."""
    return ListItem.objects.create(
        user=user,
        checklist=shopping_list,
        name=name,
        precio_unitario=Decimal(price),
        cantidad=cantidad,
        is_checked=True,
    )


def _require_row_lock() -> None:
    """El lock de fila solo existe en PostgreSQL (SQLite: no-op)."""
    if connection.vendor != "postgresql":
        pytest.skip(
            "select_for_update es un no-op en SQLite; ejecuta la suite con "
            "DJANGO_SETTINGS_MODULE=config.settings contra PostgreSQL."
        )


def _check_constraints_supported() -> None:
    """Salta el test si el motor no ejecuta CheckConstraints."""
    if not connection.features.supports_table_check_constraints:
        pytest.skip(
            "El motor no soporta CheckConstraints; la constraint solo se "
            "aplica en motores que las ejecutan."
        )


@pytest.mark.django_db
class TestChecklistCRUD:
    """GET/POST /api/checklists."""

    def test_create_with_items(self, api_client) -> None:
        """Crear una lista con productos devuelve 201 y los subtotales."""
        resp = api_client.post(
            URL,
            _list_payload(
                items=[
                    {"name": "Harina", "precio_unitario": "2.50", "cantidad": 2},
                    {"name": "Arroz", "precio_unitario": "3.00", "cantidad": 1, "is_checked": True},
                ]
            ),
            format="json",
        )
        assert resp.status_code == 201
        assert resp.data["name"] == "Mercado de la semana"
        assert resp.data["estado"] == "en_curso"
        assert len(resp.data["items"]) == 2
        # solo cuenta el marcado: 3.00 x 1
        assert resp.data["total_estimado"] == "3.00"
        assert resp.data["progress_percent"] == "50.0"

    def test_list_scoped_to_user(self, api_client) -> None:
        """Cada usuario solo ve sus listas."""
        other = UserFactory()
        ShoppingList.objects.create(user=other, name="Ajeno", currency="USD")
        ShoppingList.objects.create(user=api_client.user, name="Mía", currency="USD")
        resp = api_client.get(URL)
        assert resp.status_code == 200
        names = [row["name"] for row in resp.data["results"]]
        assert "Mía" in names
        assert "Ajeno" not in names

    def test_requires_auth(self) -> None:
        """Sin token, 401."""
        resp = APIClient().get(URL)
        assert resp.status_code in (401, 403)

    def test_detail_foreign_404(self, api_client) -> None:
        """El detalle de una lista ajena devuelve 404 (owner-scoping)."""
        other = UserFactory()
        shopping_list = ShoppingList.objects.create(user=other, name="Ajeno", currency="USD")
        resp = api_client.get(f"{URL}/{shopping_list.id}")
        assert resp.status_code == 404

    def test_toggle_item_requires_price(self, api_client) -> None:
        """Marcar un producto sin precio registrado se rechaza: 400."""
        shopping_list = ShoppingList.objects.create(
            user=api_client.user, name="Mercado", currency="USD"
        )
        item = ListItem.objects.create(
            user=api_client.user,
            checklist=shopping_list,
            name="Desconocido",
            cantidad=1,
        )
        resp = api_client.patch(
            f"{URL}/{shopping_list.id}",
            {"items": [{"id": str(item.id), "name": item.name, "is_checked": True}]},
            format="json",
        )
        assert resp.status_code == 400
        item.refresh_from_db()
        assert item.is_checked is False

    def test_uncheck_keeps_price(self, api_client) -> None:
        """Desmarcar conserva el precio registrado (para volver a tildar)."""
        shopping_list = ShoppingList.objects.create(
            user=api_client.user, name="Mercado", currency="USD"
        )
        item = ListItem.objects.create(
            user=api_client.user,
            checklist=shopping_list,
            name="Harina",
            precio_unitario=Decimal("2.50"),
            cantidad=2,
            is_checked=True,
        )
        resp = api_client.patch(
            f"{URL}/{shopping_list.id}",
            {"items": [{"id": str(item.id), "name": item.name, "is_checked": False}]},
            format="json",
        )
        assert resp.status_code == 200
        item.refresh_from_db()
        assert item.is_checked is False
        assert item.precio_unitario == Decimal("2.50")
        assert resp.data["total_estimado"] == "0.00"

    def test_currency_immutable(self, api_client) -> None:
        """No se puede cambiar la moneda de una lista existente: 400."""
        shopping_list = ShoppingList.objects.create(
            user=api_client.user, name="Mercado", currency="USD"
        )
        resp = api_client.patch(f"{URL}/{shopping_list.id}", {"currency": "VES"}, format="json")
        assert resp.status_code == 400


@pytest.mark.django_db
class TestChecklistComplete:
    """POST /api/checklists/<id>/complete."""

    def test_complete_creates_payment_and_deducts(self, api_client) -> None:
        """Completar genera un pago pagado, descuenta la cuenta y cierra la lista."""
        shopping_list = ShoppingList.objects.create(
            user=api_client.user, name="Mercado de la semana", currency="USD"
        )
        ListItem.objects.create(
            user=api_client.user,
            checklist=shopping_list,
            name="Harina",
            precio_unitario=Decimal("2.50"),
            cantidad=2,
            is_checked=True,
        )
        wallet = WalletFactory(user=api_client.user, saldo=Decimal("100.00"))

        resp = api_client.post(
            f"{URL}/{shopping_list.id}/complete",
            {"wallet": str(wallet.id), "total_real": "20.50"},
            format="json",
        )
        assert resp.status_code == 200
        assert resp.data["estado"] == "completada"
        assert resp.data["total_real"] == "20.50"
        assert resp.data["completed_at"] is not None

        wallet.refresh_from_db()
        assert wallet.saldo == Decimal("79.50")

        tx = Transaction.objects.get(user=api_client.user)
        assert tx.tipo == "pago"
        assert tx.estado == "pagado"
        assert tx.monto == Decimal("20.50")
        assert tx.moneda == "USD"
        assert tx.concepto == "Compra: Mercado de la semana"
        assert tx.wallet_id == wallet.id
        assert tx.monto_usd == Decimal("20.50")  # conversión congelada (USD = identidad)

    def test_complete_with_ves_converts_usd(self, api_client) -> None:
        """Una lista en VES congela la conversión a USD con la tasa del día."""
        ExchangeRateFactory()
        shopping_list = ShoppingList.objects.create(
            user=api_client.user, name="Mercado", currency="VES"
        )
        _add_checked_item(shopping_list, user=api_client.user, price="150.00")
        wallet = WalletFactory(user=api_client.user, currency="VES", saldo=Decimal("5000.00"))

        resp = api_client.post(
            f"{URL}/{shopping_list.id}/complete",
            {"wallet": str(wallet.id), "total_real": "1000.00"},
            format="json",
        )
        assert resp.status_code == 200
        wallet.refresh_from_db()
        assert wallet.saldo == Decimal("4000.00")
        tx = Transaction.objects.get(user=api_client.user)
        assert tx.moneda == "VES"
        assert tx.monto_usd == Decimal("10.00")  # tasa estática: 100 VES/USD
        assert Transaction.objects.count() == 1

    def test_complete_twice_rejected(self, api_client) -> None:
        """Completar dos veces devuelve 400 y no crea una segunda transacción."""
        shopping_list = ShoppingList.objects.create(
            user=api_client.user, name="Mercado", currency="USD"
        )
        _add_checked_item(shopping_list, user=api_client.user)
        wallet = WalletFactory(user=api_client.user, saldo=Decimal("100.00"))

        first = api_client.post(
            f"{URL}/{shopping_list.id}/complete",
            {"wallet": str(wallet.id), "total_real": "10.00"},
            format="json",
        )
        assert first.status_code == 200

        second = api_client.post(
            f"{URL}/{shopping_list.id}/complete",
            {"wallet": str(wallet.id), "total_real": "10.00"},
            format="json",
        )
        assert second.status_code == 400
        assert Transaction.objects.count() == 1
        wallet.refresh_from_db()
        assert wallet.saldo == Decimal("90.00")

    def test_complete_foreign_wallet_rejected(self, api_client) -> None:
        """Una cuenta de otro usuario no es válida: 400."""
        shopping_list = ShoppingList.objects.create(
            user=api_client.user, name="Mercado", currency="USD"
        )
        _add_checked_item(shopping_list, user=api_client.user)
        foreign_wallet = WalletFactory()  # de otro usuario

        resp = api_client.post(
            f"{URL}/{shopping_list.id}/complete",
            {"wallet": str(foreign_wallet.id), "total_real": "10.00"},
            format="json",
        )
        assert resp.status_code == 400
        assert not Transaction.objects.filter(user=api_client.user).exists()

    def test_complete_wrong_currency_rejected(self, api_client) -> None:
        """La cuenta debe usar la misma moneda de la lista: 400."""
        shopping_list = ShoppingList.objects.create(
            user=api_client.user, name="Mercado", currency="USD"
        )
        _add_checked_item(shopping_list, user=api_client.user)
        wallet = WalletFactory(user=api_client.user, currency="VES", saldo=Decimal("1000.00"))

        resp = api_client.post(
            f"{URL}/{shopping_list.id}/complete",
            {"wallet": str(wallet.id), "total_real": "10.00"},
            format="json",
        )
        assert resp.status_code == 400

    def test_complete_insufficient_balance_no_orphan(self, api_client) -> None:
        """Saldo insuficiente: 400, sin transacción y la lista sigue en curso.

        Garantiza que el cierre sea atómico: el fallo del descuento revierte
        también la creación de la operación (nada de egresos huérfanos).
        """
        shopping_list = ShoppingList.objects.create(
            user=api_client.user, name="Mercado", currency="USD"
        )
        _add_checked_item(shopping_list, user=api_client.user)
        wallet = WalletFactory(user=api_client.user, saldo=Decimal("5.00"))

        resp = api_client.post(
            f"{URL}/{shopping_list.id}/complete",
            {"wallet": str(wallet.id), "total_real": "10.00"},
            format="json",
        )
        assert resp.status_code == 400
        assert not Transaction.objects.filter(user=api_client.user).exists()
        assert not BalanceAuditLog.objects.filter(wallet=wallet).exists()
        shopping_list.refresh_from_db()
        assert shopping_list.estado == "en_curso"
        assert shopping_list.transaction_id is None
        wallet.refresh_from_db()
        assert wallet.saldo == Decimal("5.00")

    def test_complete_invalid_total_real(self, api_client) -> None:
        """Total real menor a 0.01 se rechaza: 400."""
        shopping_list = ShoppingList.objects.create(
            user=api_client.user, name="Mercado", currency="USD"
        )
        _add_checked_item(shopping_list, user=api_client.user)
        wallet = WalletFactory(user=api_client.user, saldo=Decimal("100.00"))

        resp = api_client.post(
            f"{URL}/{shopping_list.id}/complete",
            {"wallet": str(wallet.id), "total_real": "0"},
            format="json",
        )
        assert resp.status_code == 400
        assert not Transaction.objects.exists()

    def test_complete_requires_all_checked(self, api_client) -> None:
        """Completar exige que TODOS los productos estén marcados (integridad).

        Frontend y backend validan lo mismo: si queda un producto sin tildar,
        el cierre se rechaza y no se descuenta nada.
        """
        shopping_list = ShoppingList.objects.create(
            user=api_client.user, name="Mercado", currency="USD"
        )
        _add_checked_item(shopping_list, user=api_client.user, name="Harina")
        ListItem.objects.create(
            user=api_client.user,
            checklist=shopping_list,
            name="Pendiente",
            cantidad=1,
            is_checked=False,
        )
        wallet = WalletFactory(user=api_client.user, saldo=Decimal("100.00"))

        resp = api_client.post(
            f"{URL}/{shopping_list.id}/complete",
            {"wallet": str(wallet.id), "total_real": "10.00"},
            format="json",
        )
        assert resp.status_code == 400
        assert not Transaction.objects.filter(user=api_client.user).exists()
        assert not BalanceAuditLog.objects.filter(wallet=wallet).exists()
        shopping_list.refresh_from_db()
        assert shopping_list.estado == "en_curso"
        wallet.refresh_from_db()
        assert wallet.saldo == Decimal("100.00")

    def test_complete_rejects_checked_without_price(self, api_client) -> None:
        """Un producto marcado sin precio registrado bloquea el cierre: 400."""
        shopping_list = ShoppingList.objects.create(
            user=api_client.user, name="Mercado", currency="USD"
        )
        _add_checked_item(shopping_list, user=api_client.user, name="Harina")
        ListItem.objects.create(
            user=api_client.user,
            checklist=shopping_list,
            name="Sin precio",
            cantidad=1,
            is_checked=True,
        )
        wallet = WalletFactory(user=api_client.user, saldo=Decimal("100.00"))

        resp = api_client.post(
            f"{URL}/{shopping_list.id}/complete",
            {"wallet": str(wallet.id), "total_real": "10.00"},
            format="json",
        )
        assert resp.status_code == 400
        assert not Transaction.objects.exists()
        shopping_list.refresh_from_db()
        assert shopping_list.estado == "en_curso"

    def test_complete_rejects_empty_list(self, api_client) -> None:
        """Una lista sin productos no se puede completar: 400."""
        shopping_list = ShoppingList.objects.create(
            user=api_client.user, name="Mercado", currency="USD"
        )
        wallet = WalletFactory(user=api_client.user, saldo=Decimal("100.00"))

        resp = api_client.post(
            f"{URL}/{shopping_list.id}/complete",
            {"wallet": str(wallet.id), "total_real": "10.00"},
            format="json",
        )
        assert resp.status_code == 400
        assert not Transaction.objects.exists()
        shopping_list.refresh_from_db()
        assert shopping_list.estado == "en_curso"

    def test_edit_completed_rejected(self, api_client) -> None:
        """Una lista completada no se puede editar: 400."""
        shopping_list = ShoppingList.objects.create(
            user=api_client.user, name="Mercado", currency="USD"
        )
        _add_checked_item(shopping_list, user=api_client.user)
        wallet = WalletFactory(user=api_client.user, saldo=Decimal("100.00"))
        api_client.post(
            f"{URL}/{shopping_list.id}/complete",
            {"wallet": str(wallet.id), "total_real": "10.00"},
            format="json",
        )
        resp = api_client.patch(f"{URL}/{shopping_list.id}", {"name": "Nuevo"}, format="json")
        assert resp.status_code == 400
        shopping_list.refresh_from_db()
        assert shopping_list.name == "Mercado"

    def test_delete_completed_keeps_history(self, api_client) -> None:
        """Borrar una completada la oculta (soft-delete) sin revertir el saldo."""
        shopping_list = ShoppingList.objects.create(
            user=api_client.user, name="Mercado", currency="USD"
        )
        _add_checked_item(shopping_list, user=api_client.user)
        wallet = WalletFactory(user=api_client.user, saldo=Decimal("100.00"))
        api_client.post(
            f"{URL}/{shopping_list.id}/complete",
            {"wallet": str(wallet.id), "total_real": "10.00"},
            format="json",
        )

        resp = api_client.delete(f"{URL}/{shopping_list.id}")
        assert resp.status_code == 204

        # Soft-delete: oculta de la API, conserva el historial y la operación.
        assert not ShoppingList.objects.filter(pk=shopping_list.pk).exists()
        assert ShoppingList.all_objects.filter(pk=shopping_list.pk, is_deleted=True).exists()
        assert Transaction.objects.get(user=api_client.user).estado == "pagado"
        wallet.refresh_from_db()
        assert wallet.saldo == Decimal("90.00")


@pytest.mark.django_db
class TestChecklistCheckConstraints:
    """A10: el motor rechaza invariantes violadas (respaldo de BD)."""

    def test_completed_without_payment_rejected_by_db(self, api_client) -> None:
        """Una lista 'completada' sin cuenta ni operación lanza IntegrityError."""
        _check_constraints_supported()
        with pytest.raises(IntegrityError):
            ShoppingList.objects.create(
                user=api_client.user,
                name="Rara",
                currency="USD",
                estado="completada",
            )

    def test_negative_total_real_rejected_by_db(self, api_client) -> None:
        """total_real negativo lanza IntegrityError en el motor."""
        _check_constraints_supported()
        shopping_list = ShoppingList.objects.create(
            user=api_client.user, name="Mercado", currency="USD"
        )
        with pytest.raises(IntegrityError):
            ShoppingList.objects.filter(pk=shopping_list.pk).update(total_real=Decimal("-1.00"))

    def test_item_zero_price_rejected_by_db(self, api_client) -> None:
        """precio_unitario = 0 lanza IntegrityError en el motor."""
        _check_constraints_supported()
        shopping_list = ShoppingList.objects.create(
            user=api_client.user, name="Mercado", currency="USD"
        )
        with pytest.raises(IntegrityError):
            ListItem.objects.create(
                user=api_client.user,
                checklist=shopping_list,
                name="Gratis",
                precio_unitario=Decimal("0.00"),
            )

    def test_item_zero_quantity_rejected_by_db(self, api_client) -> None:
        """cantidad = 0 lanza IntegrityError en el motor."""
        _check_constraints_supported()
        shopping_list = ShoppingList.objects.create(
            user=api_client.user, name="Mercado", currency="USD"
        )
        with pytest.raises(IntegrityError):
            ListItem.objects.create(
                user=api_client.user, checklist=shopping_list, name="Nada", cantidad=0
            )

    def test_valid_items_still_create(self, api_client) -> None:
        """Con precios y cantidades válidas el motor no bloquea lo lícito."""
        _check_constraints_supported()
        shopping_list = ShoppingList.objects.create(
            user=api_client.user, name="Mercado", currency="USD"
        )
        item = ListItem.objects.create(
            user=api_client.user,
            checklist=shopping_list,
            name="Harina",
            precio_unitario=Decimal("2.50"),
            cantidad=2,
        )
        assert item.pk is not None


@pytest.mark.django_db(transaction=True)
class TestChecklistCompleteConcurrency:
    """Dos completaciones simultáneas → una sola operación y un descuento."""

    def test_double_complete_only_one_wins(self) -> None:
        """El lock de fila serializa: exactamente una transacción creada."""
        _require_row_lock()
        from apps.checklists.services import complete_shopping_list
        from apps.core.exceptions import BusinessRuleError

        user = UserFactory()
        shopping_list = ShoppingList.objects.create(
            user=user, name="Mercado", currency="USD"
        )
        _add_checked_item(shopping_list, user=user)
        wallet = WalletFactory(user=user, saldo=Decimal("50.00"))
        barrier = threading.Barrier(2)
        errors = []

        def worker() -> None:
            barrier.wait()
            try:
                complete_shopping_list(
                    ShoppingList.objects.get(pk=shopping_list.pk),
                    wallet=wallet,
                    total_real=Decimal("10.00"),
                )
            except BusinessRuleError as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        assert not any(t.is_alive() for t in threads)

        assert Transaction.objects.count() == 1
        wallet.refresh_from_db()
        assert wallet.saldo == Decimal("40.00")
        # El perdedor vio la lista ya completada.
        assert len(errors) == 1