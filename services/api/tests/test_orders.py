"""tests - CRM: pedidos de compra a proveedores."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from apps.business.services import create_business
from apps.crm.models import BusinessContact, Order, OrderItem, Product, StockAdjustment
from apps.notifications.models import Notification
from apps.transactions.models import Transaction
from apps.wallets.models import Wallet
from factories import UserFactory


@pytest.mark.django_db
class TestOrders:
    """Endpoints /api/business/orders/."""

    URL = "/api/business/orders/"

    @pytest.fixture
    def business(self, api_client):
        return create_business(
            api_client.user, name="Tienda Demo", currency="USD", initial_capital=Decimal("0")
        )

    @pytest.fixture
    def supplier(self, api_client, business):
        return BusinessContact.objects.create(
            user=api_client.user,
            business=business,
            name="Proveedor A",
            type="proveedor",
        )

    @pytest.fixture
    def product(self, api_client, business):
        return Product.objects.create(
            user=api_client.user,
            business=business,
            name="Aceite",
            unit="unidad",
            stock_quantity=Decimal("0"),
            unit_price=Decimal("15.00"),
            cost_price=Decimal("9.00"),
        )

    def _fund_wallet(self, business, amount: str) -> None:
        wallet = Wallet.objects.get(business=business)
        wallet.saldo = Decimal(amount)
        wallet.save()
        return wallet

    def _existing_payload(self, supplier, product_id=None, quantity="3", unit_price="20.00"):
        item = {
            "product": str(product_id),
            "description": "Producto existente",
            "quantity": quantity,
            "unit_price": unit_price,
        }
        return {"contact": str(supplier.id), "items": [item]}

    def _new_product_payload(self, supplier, **overrides):
        data = {
            "contact": str(supplier.id),
            "items": [
                {
                    "new_product": {
                        "name": "Accesorio X",
                        "sku": "",
                        "unit": "unidad",
                        "unit_price": "30.00",
                        "cost_price": "20.00",
                    },
                    "description": "",
                    "quantity": "3",
                    "unit_price": "20.00",
                }
            ],
        }
        data.update(overrides)
        return data

    def test_create_order_borrador(self, api_client, business, supplier, product) -> None:
        """POST crea un pedido PO-00001 en borrador con envio en el total."""
        resp = api_client.post(
            self.URL,
            {
                "contact": str(supplier.id),
                "shipping_amount": "10.00",
                "items": [
                    {"product": str(product.id), "description": "Linea 1", "quantity": "2", "unit_price": "100.00"},
                    {"product": str(product.id), "description": "Linea 2", "quantity": "1", "unit_price": "50.00"},
                ],
            },
            format="json",
        )
        assert resp.status_code == 201, resp.data
        assert resp.data["number"] == "PO-00001"
        assert resp.data["status"] == "borrador"
        assert resp.data["payment_state"] == "none"
        assert resp.data["subtotal"] == "250.00"
        assert resp.data["shipping_amount"] == "10.00"
        assert resp.data["total"] == "260.00"
        assert resp.data["balance_due"] == "260.00"
        assert resp.data["currency"] == "USD"
        assert resp.data["contact"]["name"] == "Proveedor A"
        assert len(resp.data["items"]) == 2

    def test_create_order_full_paid(self, api_client, business, supplier, product) -> None:
        """paid_amount == total: fase «en camino» + píldora pagado, salida de billetera."""
        wallet = self._fund_wallet(business, "1000.00")
        resp = api_client.post(
            self.URL,
            {
                "contact": str(supplier.id),
                "paid_amount": "260.00",
                "shipping_amount": "10.00",
                "items": [
                    {"product": str(product.id), "description": "Linea 1", "quantity": "2", "unit_price": "100.00"},
                    {"product": str(product.id), "description": "Linea 2", "quantity": "1", "unit_price": "50.00"},
                ],
            },
            format="json",
        )
        assert resp.status_code == 201, resp.data
        assert resp.data["status"] == "en_camino"
        assert resp.data["payment_state"] == "paid"
        assert resp.data["amount_paid"] == "260.00"
        assert resp.data["balance_due"] == "0.00"
        wallet.refresh_from_db()
        assert wallet.saldo == Decimal("740.00")
        assert Transaction.objects.filter(
            user=api_client.user, tipo="pago", wallet=wallet
        ).count() == 1
        payments = api_client.get(f"{self.URL}{resp.data['id']}/").data["payments"]
        assert len(payments) == 1

    def test_create_order_partial_paid(self, api_client, business, supplier, product) -> None:
        """Un pago parcial inicial deja la fase en camino con píldora de pago parcial."""
        self._fund_wallet(business, "1000.00")
        resp = api_client.post(
            self.URL,
            {
                "contact": str(supplier.id),
                "paid_amount": "100.00",
                "items": [
                    {"product": str(product.id), "description": "Linea", "quantity": "1", "unit_price": "250.00"}
                ],
            },
            format="json",
        )
        assert resp.status_code == 201, resp.data
        assert resp.data["status"] == "en_camino"
        assert resp.data["payment_state"] == "partial"
        assert resp.data["amount_paid"] == "100.00"
        assert resp.data["total"] == "250.00"
        assert resp.data["balance_due"] == "150.00"

    def test_paid_partial_balance(self, api_client, business, supplier, product) -> None:
        """Pago parcial con saldo pendiente correcto."""
        self._fund_wallet(business, "1000.00")
        resp = api_client.post(
            self.URL,
            {
                "contact": str(supplier.id),
                "paid_amount": "100.00",
                "items": [
                    {"product": str(product.id), "description": "Linea", "quantity": "1", "unit_price": "250.00"}
                ],
            },
            format="json",
        )
        assert resp.status_code == 201, resp.data
        assert resp.data["status"] == "en_camino"
        assert resp.data["payment_state"] == "partial"
        assert resp.data["balance_due"] == "150.00"

    def test_paid_exceeds_total(self, api_client, business, supplier, product) -> None:
        """El pago inicial no puede exceder el total."""
        resp = api_client.post(
            self.URL,
            {
                "contact": str(supplier.id),
                "paid_amount": "999.00",
                "items": [
                    {"product": str(product.id), "description": "Linea", "quantity": "1", "unit_price": "10.00"}
                ],
            },
            format="json",
        )
        assert resp.status_code == 400

    def test_requires_items(self, api_client, business, supplier) -> None:
        """El pedido debe tener al menos una linea."""
        resp = api_client.post(
            self.URL, {"contact": str(supplier.id), "items": []}, format="json"
        )
        assert resp.status_code == 400
        assert "items" in resp.data.get("errors", resp.data)

    def test_contact_must_be_supplier(self, api_client, business, supplier, product) -> None:
        """Un cliente no puede ser el proveedor del pedido."""
        client = BusinessContact.objects.create(
            user=api_client.user, business=business, name="Cliente", type="cliente"
        )
        resp = api_client.post(
            self.URL,
            {
                "contact": str(client.id),
                "items": [
                    {"product": str(product.id), "description": "Linea", "quantity": "1", "unit_price": "10.00"}
                ],
            },
            format="json",
        )
        assert resp.status_code == 400

    def test_create_with_existing_product(self, api_client, business, supplier) -> None:
        """Una linea con producto del inventario usa el cost_price por defecto."""
        prod = Product.objects.create(
            user=api_client.user,
            business=business,
            name="Grasa",
            unit="unidad",
            stock_quantity=Decimal("0"),
            unit_price=Decimal("15.00"),
            cost_price=Decimal("9.00"),
        )
        resp = api_client.post(
            self.URL,
            {
                "contact": str(supplier.id),
                "items": [
                    {"product": str(prod.id), "description": "Producto existente", "quantity": "3"}
                ],
            },
            format="json",
        )
        assert resp.status_code == 201, resp.data
        assert resp.data["items"][0]["unit_price"] == "9.00"
        assert resp.data["items"][0]["total"] == "27.00"
        prod.refresh_from_db()
        assert prod.stock_quantity == Decimal("0")
        assert prod.name == "Grasa"

    def test_receive_adds_stock_to_existing_product(self, api_client, business, supplier) -> None:
        """Recibir un pedido suma existencias al producto existente y audita."""
        prod = Product.objects.create(
            user=api_client.user,
            business=business,
            name="Aceite",
            unit="unidad",
            stock_quantity=Decimal("2.00"),
            unit_price=Decimal("15.00"),
        )
        resp = api_client.post(self.URL, self._existing_payload(supplier, prod.id), format="json")
        assert resp.status_code == 201
        order_id = resp.data["id"]
        receive = api_client.post(f"{self.URL}{order_id}/receive/")
        assert receive.status_code == 200, receive.data
        assert receive.data["status"] == "recibido"
        prod.refresh_from_db()
        assert prod.stock_quantity == Decimal("5.00")
        assert prod.name == "Aceite"
        assert prod.unit_price == Decimal("15.00")
        assert StockAdjustment.objects.filter(
            product=prod, delta=Decimal("3.00"), reason="Pedido PO-00001"
        ).count() == 1

    def test_receive_creates_new_product(self, api_client, business, supplier) -> None:
        """Recibir integra el producto nuevo al inventario con el stock recibido."""
        wallet = self._fund_wallet(business, "1000.00")
        resp = api_client.post(self.URL, self._new_product_payload(supplier), format="json")
        assert resp.status_code == 201, resp.data
        assert resp.data["items"][0]["product"] is None
        order_id = resp.data["id"]
        receive = api_client.post(f"{self.URL}{order_id}/receive/")
        assert receive.status_code == 200, receive.data
        assert receive.data["items"][0]["product"] is not None
        product = Product.objects.get(business=business, name="Accesorio X")
        assert product.user_id == api_client.user.id
        assert product.supplier_id == supplier.id
        assert product.stock_quantity == Decimal("3.00")
        assert product.cost_price == Decimal("20.00")
        assert StockAdjustment.objects.filter(product=product).count() == 1

    def test_receive_links_existing_instead_of_duplicate(self, api_client, business, supplier) -> None:
        """Si el producto nuevo ya existe solo se acumula stock, sin duplicar."""
        existing = Product.objects.create(
            user=api_client.user,
            business=business,
            name="Accesorio X",
            unit="unidad",
            stock_quantity=Decimal("2.00"),
            unit_price=Decimal("10.00"),
        )
        resp = api_client.post(self.URL, self._new_product_payload(supplier), format="json")
        assert resp.status_code == 201
        order_id = resp.data["id"]
        receive = api_client.post(f"{self.URL}{order_id}/receive/")
        assert receive.status_code == 200, receive.data
        assert Product.objects.filter(business=business, name="Accesorio X").count() == 1
        existing.refresh_from_db()
        assert existing.stock_quantity == Decimal("5.00")
        assert existing.unit_price == Decimal("10.00")
        assert existing.cost_price is None

    def test_double_receive_rejected(self, api_client, business, supplier) -> None:
        """Un pedido recibido no puede volver a recibirse."""
        prod = Product.objects.create(
            user=api_client.user,
            business=business,
            name="Aceite",
            unit="unidad",
            stock_quantity=Decimal("0"),
            unit_price=Decimal("15.00"),
        )
        order_id = api_client.post(
            self.URL, self._existing_payload(supplier, prod.id), format="json"
        ).data["id"]
        assert api_client.post(f"{self.URL}{order_id}/receive/").status_code == 200
        assert api_client.post(f"{self.URL}{order_id}/receive/").status_code == 400

    def test_cancel_draft_does_not_touch_stock(self, api_client, business, supplier) -> None:
        """Anular un borrador con producto nuevo no crea nada en inventario."""
        resp = api_client.post(self.URL, self._new_product_payload(supplier), format="json")
        assert resp.status_code == 201
        order_id = resp.data["id"]
        cancel = api_client.post(f"{self.URL}{order_id}/cancel/")
        assert cancel.status_code == 200, cancel.data
        assert cancel.data["status"] == "anulado"
        assert not Product.objects.filter(business=business, name="Accesorio X").exists()

    def test_cannot_pay_annulled(self, api_client, business, supplier, product) -> None:
        """No se puede pagar un pedido anulado."""
        self._fund_wallet(business, "1000.00")
        order_id = api_client.post(
            self.URL,
            {
                "contact": str(supplier.id),
                "items": [{"product": str(product.id), "description": "X", "quantity": "1", "unit_price": "10.00"}],
            },
            format="json",
        ).data["id"]
        api_client.post(f"{self.URL}{order_id}/cancel/")
        resp = api_client.post(f"{self.URL}{order_id}/pay/", {"amount": "10.00"})
        assert resp.status_code == 400

    def test_pay_over_balance(self, api_client, business, supplier, product) -> None:
        """No se puede pagar mas del saldo pendiente."""
        self._fund_wallet(business, "1000.00")
        order_id = api_client.post(
            self.URL,
            {
                "contact": str(supplier.id),
                "items": [{"product": str(product.id), "description": "X", "quantity": "1", "unit_price": "10.00"}],
            },
            format="json",
        ).data["id"]
        resp = api_client.post(f"{self.URL}{order_id}/pay/", {"amount": "999.00"})
        assert resp.status_code == 400

    def test_pay_full_generates_notification(self, api_client, business, supplier, product) -> None:
        """El pago que liquida el pedido lo deja pagado sin tocar su fase y notifica."""
        wallet = self._fund_wallet(business, "1000.00")
        order_id = api_client.post(
            self.URL,
            {
                "contact": str(supplier.id),
                "items": [{"product": str(product.id), "description": "X", "quantity": "1", "unit_price": "250.00"}],
            },
            format="json",
        ).data["id"]
        resp = api_client.post(f"{self.URL}{order_id}/pay/", {"amount": "250.00"})
        assert resp.status_code == 200
        assert resp.data["status"] == "borrador"
        assert resp.data["payment_state"] == "paid"
        assert resp.data["balance_due"] == "0.00"
        wallet.refresh_from_db()
        assert wallet.saldo == Decimal("750.00")
        assert Notification.objects.filter(
            user=api_client.user, kind="order_paid", scope="business"
        ).count() == 1

    def test_pay_does_not_change_phase(self, api_client, business, supplier, product) -> None:
        """Pagar un pedido en camino no lo saca de su fase: en_camino + pagado."""
        wallet = self._fund_wallet(business, "1000.00")
        order_id = api_client.post(
            self.URL,
            {
                "contact": str(supplier.id),
                "items": [{"product": str(product.id), "description": "X", "quantity": "1", "unit_price": "250.00"}],
            },
            format="json",
        ).data["id"]
        assert api_client.post(f"{self.URL}{order_id}/send/").status_code == 200
        resp = api_client.post(f"{self.URL}{order_id}/pay/", {"amount": "250.00"})
        assert resp.status_code == 200
        assert resp.data["status"] == "en_camino"
        assert resp.data["payment_state"] == "paid"

    def test_pay_partial_keeps_phase(self, api_client, business, supplier, product) -> None:
        """Un pago parcial no cambia la fase del pedido."""
        self._fund_wallet(business, "1000.00")
        order_id = api_client.post(
            self.URL,
            {
                "contact": str(supplier.id),
                "items": [{"product": str(product.id), "description": "X", "quantity": "1", "unit_price": "250.00"}],
            },
            format="json",
        ).data["id"]
        assert api_client.post(f"{self.URL}{order_id}/send/").status_code == 200
        resp = api_client.post(f"{self.URL}{order_id}/pay/", {"amount": "100.00"})
        assert resp.status_code == 200
        assert resp.data["status"] == "en_camino"
        assert resp.data["payment_state"] == "partial"
        assert resp.data["balance_due"] == "150.00"

    def test_receive_paid_order_keeps_paid_pill(self, api_client, business, supplier) -> None:
        """Recibir un pedido pagado muestra fase recibido + píldora de pagado."""
        wallet = self._fund_wallet(business, "1000.00")
        order_id = api_client.post(self.URL, self._new_product_payload(supplier), format="json").data["id"]
        paid = api_client.post(f"{self.URL}{order_id}/pay/", {"amount": "60.00"})
        assert paid.status_code == 200, paid.data
        receive = api_client.post(f"{self.URL}{order_id}/receive/")
        assert receive.status_code == 200, receive.data
        assert receive.data["status"] == "recibido"
        assert receive.data["payment_state"] == "paid"
        assert receive.data["items"][0]["product"] is not None

    def test_send_action(self, api_client, business, supplier, product) -> None:
        """POST send marca el pedido en borrador como «en camino»."""
        order_id = api_client.post(
            self.URL,
            {
                "contact": str(supplier.id),
                "items": [{"product": str(product.id), "description": "X", "quantity": "1", "unit_price": "10.00"}],
            },
            format="json",
        ).data["id"]
        resp = api_client.post(f"{self.URL}{order_id}/send/")
        assert resp.status_code == 200
        assert resp.data["status"] == "en_camino"
        assert api_client.post(f"{self.URL}{order_id}/send/").status_code == 400

    def test_update_only_borrador(self, api_client, business, supplier, product) -> None:
        """Editar borrador reemplaza lineas; los demas estados se niegan."""
        order_id = api_client.post(
            self.URL, self._existing_payload(supplier, product.id, quantity="2"), format="json"
        ).data["id"]
        sent = api_client.post(f"{self.URL}{order_id}/send/")
        assert sent.status_code == 200
        blocked = api_client.patch(
            f"{self.URL}{order_id}/",
            {"items": [{"product": str(product.id), "description": "Nueva", "quantity": "9", "unit_price": "5.00"}]},
            format="json",
        )
        assert blocked.status_code == 400
        canceled = api_client.post(f"{self.URL}{order_id}/cancel/")
        assert canceled.status_code == 200

    def test_delete_only_borrador_without_payments(self, api_client, business, supplier, product) -> None:
        """Borrado permitido solo en borrador y sin pagos."""
        order_id = api_client.post(
            self.URL,
            {
                "contact": str(supplier.id),
                "items": [{"product": str(product.id), "description": "X", "quantity": "1", "unit_price": "10.00"}],
            },
            format="json",
        ).data["id"]
        assert api_client.delete(f"{self.URL}{order_id}/").status_code == 204
        self._fund_wallet(business, "1000.00")
        order_id = api_client.post(
            self.URL,
            {
                "contact": str(supplier.id),
                "paid_amount": "10.00",
                "items": [{"product": str(product.id), "description": "X", "quantity": "1", "unit_price": "10.00"}],
            },
            format="json",
        ).data["id"]
        assert api_client.delete(f"{self.URL}{order_id}/").status_code == 400

    def test_product_and_new_product_mutually_exclusive(self, api_client, business, supplier) -> None:
        """Una linea no puede llevar producto y producto nuevo a la vez."""
        payload = {
            "contact": str(supplier.id),
            "items": [
                {
                    "product": str(Product.objects.create(
                        user=api_client.user,
                        business=business,
                        name="Aceite",
                        unit="unidad",
                        stock_quantity=Decimal("0"),
                        unit_price=Decimal("15.00"),
                    ).id),
                    "new_product": {"name": "Otro", "unit": "unidad", "unit_price": "5.00"},
                    "description": "X",
                    "quantity": "1",
                    "unit_price": "10.00",
                }
            ],
        }
        resp = api_client.post(self.URL, payload, format="json")
        assert resp.status_code == 400

    def test_new_product_requires_name(self, api_client, business, supplier) -> None:
        """El producto nuevo sin nombre es rechazado."""
        payload = {
            "contact": str(supplier.id),
            "items": [
                {
                    "new_product": {"sku": "S1", "unit": "unidad", "unit_price": "5.00"},
                    "description": "X",
                    "quantity": "1",
                    "unit_price": "10.00",
                }
            ],
        }
        resp = api_client.post(self.URL, payload, format="json")
        assert resp.status_code == 400

    def test_integer_quantity_for_unidad(self, api_client, business, supplier) -> None:
        """Los productos por unidad exigen cantidades enteras en ambos modos."""
        prod = Product.objects.create(
            user=api_client.user,
            business=business,
            name="Aceite",
            unit="unidad",
            stock_quantity=Decimal("0"),
            unit_price=Decimal("15.00"),
        )
        resp = api_client.post(
            self.URL, self._existing_payload(supplier, prod.id, quantity="1.5")
        )
        assert resp.status_code == 400
        payload = {
            "contact": str(supplier.id),
            "items": [
                {
                    "new_product": {"name": "Nuevo", "unit": "unidad", "unit_price": "5.00"},
                    "description": "X",
                    "quantity": "1.5",
                    "unit_price": "10.00",
                }
            ],
        }
        resp = api_client.post(self.URL, payload, format="json")
        assert resp.status_code == 400

    def test_cannot_access_other_user(self, api_client, supplier) -> None:
        """Un usuario no accede a pedidos ajenos."""
        other = UserFactory()
        other_business = create_business(
            other, name="Otra", currency="USD", initial_capital=Decimal("0")
        )
        other_supplier = BusinessContact.objects.create(
            user=other, business=other_business, name="Otra", type="proveedor"
        )
        order = Order.objects.create(
            user=other,
            business=other_business,
            contact=other_supplier,
            number="PO-00001",
            order_date=date.today(),
            status="borrador",
            subtotal=Decimal("10.00"),
            total=Decimal("10.00"),
            balance_due=Decimal("10.00"),
        )
        assert api_client.get(f"{self.URL}{order.id}/").status_code == 404
        assert (
            api_client.post(f"{self.URL}{order.id}/pay/", {"amount": "1"}).status_code
            == 404
        )