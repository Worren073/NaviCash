"""tests — CRM: inventario conectado a facturación."""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.business.services import create_business
from apps.crm.models import BusinessContact, Product, ProductCategory, StockAdjustment
from apps.notifications.models import Notification


@pytest.mark.django_db
class TestInventory:
    """Endpoints /api/business/products/ y /api/business/product-categories/."""

    URL = "/api/business/products/"
    CAT_URL = "/api/business/product-categories/"

    @pytest.fixture
    def business(self, api_client):
        return create_business(
            api_client.user, name="Tienda Demo", currency="USD", initial_capital=Decimal("0")
        )

    @pytest.fixture
    def category(self, api_client, business):
        return ProductCategory.objects.create(
            user=api_client.user, business=business, name="Abarrotes"
        )

    @pytest.fixture
    def supplier(self, api_client, business):
        return BusinessContact.objects.create(
            user=api_client.user, business=business, name="Distribuidora", type="proveedor"
        )

    def _product_payload(self, **overrides):
        data = {
            "name": "Arroz 1kg",
            "sku": "ARZ-01",
            "unit": "kilogramo",
            "unit_price": "1.50",
            "stock_quantity": "50",
        }
        data.update(overrides)
        return data

    def _build_product(self, api_client, business, **kwargs):
        fields = {
            "user": api_client.user,
            "business": business,
            "name": "Arroz 1kg",
            "sku": "ARZ-01",
            "unit": "kilogramo",
            "unit_price": Decimal("1.50"),
            "stock_quantity": Decimal("50"),
        }
        fields.update(kwargs)
        return Product.objects.create(**fields)

    # --- CRUD ---

    def test_create_product(self, api_client, business, category, supplier) -> None:
        """POST /products/ crea el producto con stock inicial y referencias."""
        resp = api_client.post(
            self.URL,
            self._product_payload(
                category=str(category.id),
                supplier=str(supplier.id),
                low_stock_threshold="10",
            ),
            format="json",
        )
        assert resp.status_code == 201, resp.data
        assert resp.data["name"] == "Arroz 1kg"
        assert resp.data["stock_quantity"] == "50.00"
        assert resp.data["category"] == category.id
        assert resp.data["supplier"] == supplier.id
        assert resp.data["is_low_stock"] is False

    def test_unique_name_case_insensitive(self, api_client, business) -> None:
        """No se puede repetir el nombre del producto (ignora mayúsculas)."""
        self._build_product(api_client, business)
        resp = api_client.post(
            self.URL, self._product_payload(name="arroz 1kg"), format="json"
        )
        assert resp.status_code == 400
        assert "producto" in str(resp.data["detail"]).lower()

    def test_unique_sku(self, api_client, business) -> None:
        """No se puede repetir el SKU dentro del negocio."""
        self._build_product(api_client, business)
        resp = api_client.post(
            self.URL, self._product_payload(name="Pan", sku="ARZ-01"), format="json"
        )
        assert resp.status_code == 400
        assert "sku" in str(resp.data["detail"]).lower()

    def test_cannot_create_negative_stock(self, api_client, business) -> None:
        """El stock inicial no puede ser negativo."""
        resp = api_client.post(
            self.URL, self._product_payload(stock_quantity="-5"), format="json"
        )
        assert resp.status_code == 400

    def test_list_search_and_filter(self, api_client, business, category) -> None:
        """GET filtra por búsqueda, categoría y estado activo."""
        self._build_product(api_client, business, name="Arroz 1kg", sku="ARZ-01")
        self._build_product(
            api_client, business, name="Fideos", sku="FID-02", is_active=False
        )
        assert len(api_client.get(self.URL).data["results"]) == 2
        assert len(api_client.get(f"{self.URL}?search=arroz").data["results"]) == 1
        assert (
            len(api_client.get(f"{self.URL}?search=FID").data["results"]) == 1
        )
        assert len(api_client.get(f"{self.URL}?active=false").data["results"]) == 1
        assert len(api_client.get(f"{self.URL}?category={category.id}").data["results"]) == 0

    def test_update_keeps_stock(self, api_client, business) -> None:
        """PATCH no toca existencias: el stock solo cambia por /adjust/."""
        product = self._build_product(api_client, business)
        resp = api_client.patch(
            f"{self.URL}{product.id}/", {"unit_price": "2.00"}, format="json"
        )
        assert resp.status_code == 200
        product.refresh_from_db()
        assert product.unit_price == Decimal("2.00")
        assert product.stock_quantity == Decimal("50")

    def test_cannot_access_other_user(self, api_client) -> None:
        """Un usuario no ve productos de otro negocio."""
        from factories import UserFactory

        other = UserFactory()
        other_business = create_business(
            other, name="Otra", currency="USD", initial_capital=Decimal("0")
        )
        product = Product.objects.create(
            user=other,
            business=other_business,
            name="Ajeno",
            unit="unidad",
            unit_price=Decimal("1.00"),
            stock_quantity=Decimal("10"),
        )
        assert api_client.get(self.URL).data["results"] == []
        assert api_client.get(f"{self.URL}{product.id}/").status_code == 404

    # --- Ajuste de existencias ---

    def test_adjust_action(self, api_client, business) -> None:
        """POST /adjust/ actualiza stock y registra el movimiento auditado."""
        product = self._build_product(api_client, business)
        resp = api_client.post(
            f"{self.URL}{product.id}/adjust/", {"delta": "10", "reason": "Reposición"}
        )
        assert resp.status_code == 200
        product.refresh_from_db()
        assert product.stock_quantity == Decimal("60")
        assert StockAdjustment.objects.filter(
            product=product, delta=Decimal("10"), reason="Reposición"
        ).count() == 1

    def test_adjust_requires_reason(self, api_client, business) -> None:
        """Todo ajuste requiere un motivo."""
        product = self._build_product(api_client, business)
        resp = api_client.post(
            f"{self.URL}{product.id}/adjust/", {"delta": "5", "reason": ""}
        )
        assert resp.status_code == 400

    def test_adjust_cannot_go_negative(self, api_client, business) -> None:
        """El ajuste no puede dejar el stock negativo."""
        product = self._build_product(api_client, business, stock_quantity=Decimal("3"))
        resp = api_client.post(
            f"{self.URL}{product.id}/adjust/", {"delta": "-5", "reason": "Merma"}
        )
        assert resp.status_code == 400
        product.refresh_from_db()
        assert product.stock_quantity == Decimal("3")

    # --- Descuento y reposición de stock por facturas ---

    def test_invoice_withdraws_stock(self, api_client, business) -> None:
        """Crear factura con producto descuenta stock y audita el movimiento."""
        product = self._build_product(api_client, business, stock_quantity=Decimal("50"))
        contact = BusinessContact.objects.create(
            user=api_client.user, business=business, name="Cliente A", type="cliente"
        )
        resp = api_client.post(
            "/api/business/invoices/",
            {
                "contact": str(contact.id),
                "items": [
                    {
                        "product": str(product.id),
                        "description": "Arroz 1kg",
                        "quantity": "10",
                    }
                ],
            },
            format="json",
        )
        assert resp.status_code == 201, resp.data
        assert resp.data["items"][0]["unit_price"] == "1.50"
        product.refresh_from_db()
        assert product.stock_quantity == Decimal("40")
        assert StockAdjustment.objects.filter(
            product=product, delta=Decimal("-10")
        ).count() == 1

    def test_invoice_uses_wholesale_price(self, api_client, business) -> None:
        """Cliente mayorista usa el precio mayorista del producto."""
        wholesale = self._build_product(
            api_client,
            business,
            name="Caja 50kg",
            sku="CAJ-50",
            unit_price=Decimal("1.50"),
            wholesale_price=Decimal("1.20"),
        )
        mayorista = BusinessContact.objects.create(
            user=api_client.user,
            business=business,
            name="Venta Core",
            type="cliente",
            customer_type="mayorista",
        )
        resp = api_client.post(
            "/api/business/invoices/",
            {
                "contact": str(mayorista.id),
                "items": [
                    {
                        "product": str(wholesale.id),
                        "description": "Caja 50kg",
                        "quantity": "20",
                    }
                ],
            },
            format="json",
        )
        assert resp.status_code == 201, resp.data
        assert resp.data["items"][0]["unit_price"] == "1.20"
        assert resp.data["total"] == "24.00"

    def test_block_sale_over_stock(self, api_client, business) -> None:
        """Se bloquea la venta cuando la cantidad supera las existencias."""
        product = self._build_product(api_client, business, stock_quantity=Decimal("5"))
        contact = BusinessContact.objects.create(
            user=api_client.user, business=business, name="Cliente A", type="cliente"
        )
        resp = api_client.post(
            "/api/business/invoices/",
            {
                "contact": str(contact.id),
                "items": [
                    {"product": str(product.id), "description": "Arroz", "quantity": "6"}
                ],
            },
            format="json",
        )
        assert resp.status_code == 400
        assert "stock insuficiente" in str(resp.data["detail"]).lower()
        product.refresh_from_db()
        assert product.stock_quantity == Decimal("5")

    def test_cancel_restocks(self, api_client, business) -> None:
        """Anular una factura emitida repone las existencias."""
        product = self._build_product(api_client, business, stock_quantity=Decimal("50"))
        contact = BusinessContact.objects.create(
            user=api_client.user, business=business, name="Cliente A", type="cliente"
        )
        invoice = api_client.post(
            "/api/business/invoices/",
            {
                "contact": str(contact.id),
                "items": [
                    {"product": str(product.id), "description": "Arroz", "quantity": "10"}
                ],
            },
            format="json",
        ).data
        product.refresh_from_db()
        assert product.stock_quantity == Decimal("40")

        resp = api_client.post(
            f"/api/business/invoices/{invoice['id']}/cancel/"
        )
        assert resp.status_code == 200
        product.refresh_from_db()
        assert product.stock_quantity == Decimal("50")
        assert StockAdjustment.objects.filter(
            product=product, delta=Decimal("10")
        ).count() == 1

    def test_delete_restocks(self, api_client, business) -> None:
        """Borrar una factura sin pagos que descontó stock lo repone."""
        product = self._build_product(api_client, business, stock_quantity=Decimal("50"))
        contact = BusinessContact.objects.create(
            user=api_client.user, business=business, name="Cliente A", type="cliente"
        )
        invoice = api_client.post(
            "/api/business/invoices/",
            {
                "contact": str(contact.id),
                "items": [
                    {"product": str(product.id), "description": "Arroz", "quantity": "10"}
                ],
            },
            format="json",
        ).data
        assert api_client.delete(f"/api/business/invoices/{invoice['id']}/").status_code == 204
        product.refresh_from_db()
        assert product.stock_quantity == Decimal("50")

    # --- Notificación de stock bajo ---

    def test_low_stock_notification(self, api_client, business) -> None:
        """refresh_notifications crea la alerta de stock bajo (una por día)."""
        self._build_product(
            api_client, business, stock_quantity=Decimal("4"), low_stock_threshold=Decimal("10")
        )
        from apps.notifications.services import refresh_notifications

        result = refresh_notifications(api_client.user, scope="business")
        assert any(n.kind == "product_low_stock" for n in result)
        assert Notification.objects.filter(
            user=api_client.user, kind="product_low_stock", scope="business"
        ).count() == 1

    def test_no_low_stock_without_threshold(self, api_client, business) -> None:
        """Sin umbral definido no hay alerta de stock bajo."""
        self._build_product(api_client, business, stock_quantity=Decimal("4"))
        from apps.notifications.services import refresh_notifications

        refresh_notifications(api_client.user, scope="business")
        assert Notification.objects.filter(
            user=api_client.user, kind="product_low_stock"
        ).count() == 0