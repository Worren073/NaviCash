"""tests — Fase 2: origen de operaciones, auto-categorías del CRM y costos congelados.

Cubre:
- ``Transaction.origen`` según el flujo que la generó (manual, CRM, mensualidad,
  lista de compras, transferencia).
- Auto-categoría de cobros/pagos del CRM usando las categorías por defecto del
  usuario (cobro → "Venta", pago → "Otros").
- Suscripciones: ``amount``/``currency`` opcionales y su validación.
- Pedidos: ``due_date`` por defecto desde los días de crédito del proveedor,
  ``received_at`` al recibir y ``cost_price`` congelado en líneas.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from apps.business.services import create_business
from apps.checklists.models import ListItem, ShoppingList
from apps.checklists.services import complete_shopping_list
from apps.crm.models import BusinessContact, Product
from apps.crm.services import (
    create_invoice,
    create_order,
    receive_order,
    record_invoice_payment,
    record_order_payment,
)
from apps.subscriptions.models import Subscription
from apps.subscriptions.services import renew_subscription
from apps.transactions.models import Category, Transaction
from apps.transactions.services import create_transfer, register_transaction
from apps.wallets.models import Wallet
from factories import UserFactory, WalletFactory


@pytest.mark.django_db
class TestTransactionOrigin:
    """El campo ``origen`` distingue el flujo que creó cada operación."""

    def test_manual_api_defaults_to_manual(self, api_client) -> None:
        """Alta manual por la API → origen "manual" (por defecto)."""
        wallet = WalletFactory(user=api_client.user, saldo=Decimal("100.00"))
        resp = api_client.post(
            "/api/transactions",
            {
                "tipo": "pago",
                "monto": "10.00",
                "moneda": "USD",
                "wallet": str(wallet.id),
                "concepto": "Cafetería",
                "estado": "pagado",
            },
            format="json",
        )
        assert resp.status_code == 201, resp.data
        assert resp.data["origen"] == "manual"

    def test_register_transaction_defaults_to_manual(self, api_client) -> None:
        """La función de servicio también nace como manual sin categoría."""
        wallet = WalletFactory(user=api_client.user, saldo=Decimal("100.00"))
        tx = register_transaction(
            api_client.user,
            tipo="pago",
            monto=Decimal("10.00"),
            moneda="USD",
            wallet=wallet,
        )
        assert tx.origen == "manual"
        assert tx.category is None

    def test_transfer_origen(self, api_client) -> None:
        """Las transferencias entre cuentas marcan origen "transfer"."""
        source = WalletFactory(user=api_client.user, saldo=Decimal("100.00"))
        dest = WalletFactory(user=api_client.user, saldo=Decimal("0.00"))
        tx = create_transfer(source, dest, Decimal("30.00"))
        assert tx.origen == "transfer"

    def test_subscription_renew_origen(self, api_client) -> None:
        """Renovar una mensualidad marca origen "subscription"."""
        today = date.today()
        subscription = Subscription.objects.create(
            user=api_client.user,
            name="Netflix",
            start_date=today - timedelta(days=30),
            end_date=today - timedelta(days=1),
        )
        wallet = WalletFactory(user=api_client.user, saldo=Decimal("100.00"))
        renew_subscription(subscription, wallet, Decimal("10.00"))
        tx = Transaction.objects.get(concepto="Renovación: Netflix")
        assert tx.origen == "subscription"

    def test_checklist_complete_origen(self, api_client) -> None:
        """Completar una lista de compras marca origen "checklist"."""
        shopping_list = ShoppingList.objects.create(
            user=api_client.user,
            name="Mercado",
            currency="USD",
        )
        ListItem.objects.create(
            user=api_client.user,
            checklist=shopping_list,
            name="Arroz",
            precio_unitario=Decimal("5.00"),
            cantidad=2,
            is_checked=True,
        )
        wallet = WalletFactory(user=api_client.user, saldo=Decimal("100.00"))
        complete_shopping_list(shopping_list, wallet, Decimal("10.00"))
        tx = Transaction.objects.get(concepto="Compra: Mercado")
        assert tx.origen == "checklist"


@pytest.mark.django_db
class TestCrmOriginAndAutoCategory:
    """Cobros/pagos del CRM marcan su origen y caen en la categoría por defecto."""

    def _business(self, user) -> tuple:
        business = create_business(
            user, name="Tienda Demo", currency="USD", initial_capital=Decimal("0")
        )
        contact = BusinessContact.objects.create(
            user=user,
            business=business,
            name="Cliente A",
            type="cliente",
        )
        return business, contact

    def test_invoice_payment_origin_and_category(self, api_client) -> None:
        """Cobro de factura → origen crm_invoice y categoría "Venta"."""
        business, contact = self._business(api_client.user)
        invoice = create_invoice(
            api_client.user,
            business,
            contact,
            [{"description": "Servicio", "quantity": 1, "unit_price": "100.00"}],
        )
        payment = record_invoice_payment(invoice, Decimal("60.00"))
        tx = payment.transaction
        assert tx.origen == "crm_invoice"
        assert tx.category is not None
        assert tx.category.name == "Venta"
        assert tx.category.tipo == "ingreso"

    def test_order_payment_origin_and_category(self, api_client) -> None:
        """Pago de pedido → origen crm_order y categoría "Otros"."""
        business, contact = self._business(api_client.user)
        contact.type = "proveedor"
        contact.save()
        order = create_order(
            api_client.user,
            business,
            contact,
            [{"description": "Mercancía", "quantity": 2, "unit_price": "20.00"}],
        )
        wallet = Wallet.objects.get(business=business)
        wallet.saldo = Decimal("500.00")
        wallet.save()
        payment = record_order_payment(order, Decimal("40.00"))
        tx = payment.transaction
        assert tx.origen == "crm_order"
        assert tx.category is not None
        assert tx.category.name == "Otros"
        assert tx.category.tipo == "egreso"

    def test_auto_category_respects_custom_mapping(self, api_client) -> None:
        """Si el usuario borró "Venta", el cobro queda sin categoría (fallback)."""
        Category.objects.filter(user=api_client.user, name="Venta").delete()
        business, contact = self._business(api_client.user)
        invoice = create_invoice(
            api_client.user,
            business,
            contact,
            [{"description": "Servicio", "quantity": 1, "unit_price": "100.00"}],
        )
        payment = record_invoice_payment(invoice, Decimal("60.00"))
        tx = payment.transaction
        assert tx.origen == "crm_invoice"
        assert tx.category is None

    def test_initial_invoice_payment_gets_category(self, api_client) -> None:
        """El pago inicial al emitir una factura también es un cobro del CRM."""
        business, contact = self._business(api_client.user)
        invoice = create_invoice(
            api_client.user,
            business,
            contact,
            [{"description": "Servicio", "quantity": 1, "unit_price": "100.00"}],
            paid_amount=Decimal("100.00"),
        )
        assert invoice.payments.count() == 1
        assert invoice.payments.first().transaction.origen == "crm_invoice"
        assert invoice.payments.first().transaction.category.name == "Venta"


@pytest.mark.django_db
class TestFrozenCostsAndOrderDates:
    """Costos congelados y fechas de pedido (due_date / received_at)."""

    def _setup(self, api_client):
        user = api_client.user
        business = create_business(
            user, name="Tienda Demo", currency="USD", initial_capital=Decimal("0")
        )
        supplier = BusinessContact.objects.create(
            user=user,
            business=business,
            name="Proveedor A",
            type="proveedor",
            payment_terms_days=15,
        )
        product = Product.objects.create(
            user=user,
            business=business,
            name="Aceite",
            unit="unidad",
            stock_quantity=Decimal("10"),
            unit_price=Decimal("15.00"),
            cost_price=Decimal("9.00"),
        )
        return business, supplier, product

    def test_invoice_item_freezes_cost(self, api_client) -> None:
        """La línea de factura congela el costo del producto al emitirla."""
        business, contact, product = self._setup(api_client)
        invoice = create_invoice(
            api_client.user,
            business,
            contact,
            [
                {"product": product, "description": "Aceite", "quantity": 2, "unit_price": "15.00"},
                {"description": "Flete", "quantity": 1, "unit_price": "5.00"},
            ],
        )
        oil_line = invoice.items.get(description="Aceite")
        freight_line = invoice.items.get(description="Flete")
        assert oil_line.cost_price == Decimal("9.00")
        # Línea sin producto del catálogo → sin costo congelado.
        assert freight_line.cost_price is None

    def test_order_freezes_cost_from_product(self, api_client) -> None:
        """La línea de pedido congela el costo del producto existente."""
        business, supplier, product = self._setup(api_client)
        order = create_order(
            api_client.user,
            business,
            supplier,
            [{"product": product, "description": "Aceite", "quantity": 3, "unit_price": "20.00"}],
        )
        item = order.items.get()
        assert item.cost_price == Decimal("9.00")

    def test_order_freezes_cost_from_new_product(self, api_client) -> None:
        """El pedido de producto nuevo usa su cost_price declarado."""
        business, supplier, _ = self._setup(api_client)
        order = create_order(
            api_client.user,
            business,
            supplier,
            [
                {
                    "description": "Accesorio X",
                    "quantity": 3,
                    "unit_price": "30.00",
                    "new_product": {
                        "name": "Accesorio X",
                        "sku": "",
                        "unit": "unidad",
                        "unit_price": "30.00",
                        "cost_price": "20.00",
                    },
                }
            ],
        )
        assert order.items.get().cost_price == Decimal("20.00")

    def test_order_due_date_from_terms(self, api_client) -> None:
        """Sin due_date, se calcula desde los días de crédito del proveedor."""
        business, supplier, _ = self._setup(api_client)
        order = create_order(
            api_client.user,
            business,
            supplier,
            [{"description": "Mercancía", "quantity": 1, "unit_price": "10.00"}],
            order_date=date(2026, 10, 1),
        )
        assert order.due_date == date(2026, 10, 16)

    def test_explicit_due_date_wins(self, api_client) -> None:
        """Un due_date explícito no es reemplazado por los días de crédito."""
        business, supplier, _ = self._setup(api_client)
        order = create_order(
            api_client.user,
            business,
            supplier,
            [{"description": "Mercancía", "quantity": 1, "unit_price": "10.00"}],
            due_date=date(2026, 12, 1),
        )
        assert order.due_date == date(2026, 12, 1)

    def test_receive_sets_received_at(self, api_client) -> None:
        """Recibir el pedido fija received_at."""
        business, supplier, product = self._setup(api_client)
        order = create_order(
            api_client.user,
            business,
            supplier,
            [{"product": product, "description": "Aceite", "quantity": 1, "unit_price": "10.00"}],
        )
        assert order.received_at is None
        receive_order(order)
        order.refresh_from_db()
        assert order.status == "recibido"
        assert order.received_at is not None

    def test_order_due_date_validation(self, api_client) -> None:
        """La API rechaza un due_date anterior a la fecha del pedido."""
        business, supplier, product = self._setup(api_client)
        resp = api_client.post(
            "/api/business/orders/",
            {
                "contact": str(supplier.id),
                "order_date": "2026-10-01",
                "due_date": "2026-09-01",
                "items": [
                    {
                        "product": str(product.id),
                        "description": "Aceite",
                        "quantity": 1,
                        "unit_price": "15.00",
                    }
                ],
            },
            format="json",
        )
        assert resp.status_code == 400
        assert "due_date" in resp.data["errors"]


@pytest.mark.django_db
class TestSubscriptionAmount:
    """Suscripciones: amount/currency opcional y validación."""

    URL = "/api/subscriptions"

    def _payload(self, **overrides) -> dict:
        payload = {
            "name": "Gimnasio",
            "color": "#10b981",
            "start_date": "2026-07-01",
            "end_date": "2026-09-30",
        }
        payload.update(overrides)
        return payload

    def test_amount_with_currency(self, api_client) -> None:
        """Con amount y currency se persisten en el serializador."""
        resp = api_client.post(
            self.URL,
            self._payload(amount="25.00", currency="VES"),
        )
        assert resp.status_code == 201, resp.data
        assert resp.data["amount"] == "25.00"
        assert resp.data["currency"] == "VES"

    def test_amount_optional_defaults_usd(self, api_client) -> None:
        """Sin amount queda nulo y la moneda por defecto es USD."""
        resp = api_client.post(self.URL, self._payload())
        assert resp.status_code == 201, resp.data
        assert resp.data["amount"] is None
        assert resp.data["currency"] == "USD"

    def test_negative_amount_rejected(self, api_client) -> None:
        """Un amount no positivo se rechaza con 400."""
        resp = api_client.post(self.URL, self._payload(amount="-5.00"))
        assert resp.status_code == 400
        assert "amount" in resp.data["errors"]