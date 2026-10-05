"""tests — CRM: clientes y proveedores del negocio."""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.business.services import create_business
from apps.crm.models import BusinessContact
from factories import UserFactory


@pytest.mark.django_db
class TestBusinessContact:
    """Endpoints /api/business/contacts."""

    URL = "/api/business/contacts/"

    @pytest.fixture
    def business(self, api_client):
        return create_business(
            api_client.user, name="Tienda Demo", currency="USD", initial_capital=Decimal("0")
        )

    def test_create_contact(self, api_client, business) -> None:
        """POST crea un contacto asociado al negocio del usuario."""
        resp = api_client.post(
            self.URL,
            {
                "name": "Cliente Mayorista",
                "type": "cliente",
                "customer_type": "mayorista",
                "email": "cliente@example.com",
                "phone": "04121234567",
                "payment_terms_days": 15,
            },
        )
        assert resp.status_code == 201
        assert resp.data["name"] == "Cliente Mayorista"
        assert resp.data["business"] == business.id
        assert resp.data["type"] == "cliente"
        assert resp.data["customer_type"] == "mayorista"
        assert BusinessContact.objects.filter(user=api_client.user).count() == 1

    def test_list_contacts(self, api_client, business) -> None:
        """GET devuelve solo los contactos del usuario."""
        BusinessContact.objects.create(
            user=api_client.user,
            business=business,
            name="A",
            type="cliente",
        )
        other = UserFactory()
        other_business = create_business(
            other, name="Otro", currency="USD", initial_capital=Decimal("0")
        )
        BusinessContact.objects.create(
            user=other, business=other_business, name="B", type="proveedor"
        )

        resp = api_client.get(self.URL)
        assert resp.status_code == 200
        assert len(resp.data["results"]) == 1
        assert resp.data["results"][0]["name"] == "A"

    def test_search_contacts(self, api_client, business) -> None:
        """?search filtra por nombre, email, teléfono y RIF."""
        BusinessContact.objects.create(
            user=api_client.user,
            business=business,
            name="Pedro Pérez",
            email="pedro@example.com",
            phone="04121234567",
            tax_id="J-12345678-9",
            type="cliente",
        )
        BusinessContact.objects.create(
            user=api_client.user,
            business=business,
            name="Otro",
            type="proveedor",
        )

        for term in ["Pedro", "pedro@example", "04121234567", "J-12345678"]:
            resp = api_client.get(f"{self.URL}?search={term}")
            assert resp.status_code == 200
            assert len(resp.data["results"]) == 1, term
            assert resp.data["results"][0]["name"] == "Pedro Pérez"

    def test_type_filter(self, api_client, business) -> None:
        """?type filtra por tipo de contacto."""
        BusinessContact.objects.create(
            user=api_client.user, business=business, name="Cliente", type="cliente"
        )
        BusinessContact.objects.create(
            user=api_client.user, business=business, name="Proveedor", type="proveedor"
        )
        resp = api_client.get(f"{self.URL}?type=proveedor")
        assert resp.status_code == 200
        assert len(resp.data["results"]) == 1
        assert resp.data["results"][0]["name"] == "Proveedor"

    def test_update_contact(self, api_client, business) -> None:
        """PATCH actualiza un contacto."""
        contact = BusinessContact.objects.create(
            user=api_client.user, business=business, name="Antes", type="cliente"
        )
        resp = api_client.patch(
            f"{self.URL}{contact.id}/", {"name": "Después", "payment_terms_days": 30}
        )
        assert resp.status_code == 200
        assert resp.data["name"] == "Después"
        assert resp.data["payment_terms_days"] == 30

    def test_delete_contact(self, api_client, business) -> None:
        """DELETE elimina el contacto."""
        contact = BusinessContact.objects.create(
            user=api_client.user, business=business, name="Borrar", type="cliente"
        )
        resp = api_client.delete(f"{self.URL}{contact.id}/")
        assert resp.status_code == 204
        assert not BusinessContact.objects.filter(pk=contact.pk).exists()

    def test_cannot_access_other_user_contact(self, api_client, business) -> None:
        """Un usuario no puede ver/editar/borrar contactos ajenos."""
        other = UserFactory()
        other_business = create_business(
            other, name="Otro", currency="USD", initial_capital=Decimal("0")
        )
        contact = BusinessContact.objects.create(
            user=other, business=other_business, name="Ajenos", type="cliente"
        )

        assert api_client.get(f"{self.URL}{contact.id}/").status_code == 404
        assert (
            api_client.patch(f"{self.URL}{contact.id}/", {"name": "X"}).status_code
            == 404
        )
        assert api_client.delete(f"{self.URL}{contact.id}/").status_code == 404

    def test_name_required(self, api_client, business) -> None:
        """El nombre es obligatorio."""
        resp = api_client.post(self.URL, {"name": "   ", "type": "cliente"})
        assert resp.status_code == 400
        errors = resp.data.get("errors", resp.data)
        assert "name" in errors

    def test_customer_type_not_for_supplier(self, api_client, business) -> None:
        """customer_type no puede usarse si el tipo es proveedor."""
        resp = api_client.post(
            self.URL,
            {
                "name": "Proveedor",
                "type": "proveedor",
                "customer_type": "mayorista",
            },
        )
        assert resp.status_code == 400
        errors = resp.data.get("errors", resp.data)
        assert "customer_type" in errors

    def test_credit_limit_validation(self, api_client, business) -> None:
        """El límite de crédito debe ser > 0 si se envía."""
        resp = api_client.post(
            self.URL,
            {
                "name": "Cliente",
                "type": "cliente",
                "credit_limit": "0.00",
                "currency": "USD",
            },
        )
        assert resp.status_code == 400
        errors = resp.data.get("errors", resp.data)
        assert "credit_limit" in errors

    def test_tax_id_unique_per_business(self, api_client, business) -> None:
        """No puede haber dos contactos con el mismo RIF en el mismo negocio."""
        BusinessContact.objects.create(
            user=api_client.user,
            business=business,
            name="A",
            type="cliente",
            tax_id="J-123456789",
        )
        resp = api_client.post(
            self.URL,
            {
                "name": "B",
                "type": "cliente",
                "tax_id": "J-123456789",
            },
        )
        assert resp.status_code == 400

    # --- Cédula/RIF: prefijo V/J/E, formato y unicidad ---

    def test_tax_id_normalized_on_create(self, api_client, business) -> None:
        """La cédula se guarda en formato canónico PREFIJO-NÚMERO."""
        resp = api_client.post(
            self.URL,
            {"name": "Pedro", "type": "cliente", "tax_id": "  v12345678  "},
        )
        assert resp.status_code == 201, resp.data
        assert resp.data["tax_id"] == "V-12345678"

    @pytest.mark.parametrize(
        ("raw", "fragmento"),
        [
            ("V123", "6 a 8 dígitos"),
            ("J123", "9 a 11 dígitos"),
            ("VABCDEFG", "6 a 8 dígitos"),
            ("E1234", "5 a 12 caracteres"),
            ("X12345678", "V, J o E"),
        ],
    )
    def test_tax_id_format_rejected(self, api_client, business, raw, fragmento) -> None:
        """Cada tipo de cédula valida el formato de su número."""
        resp = api_client.post(
            self.URL, {"name": "X", "type": "cliente", "tax_id": raw}
        )
        assert resp.status_code == 400
        assert fragmento.lower() in str(resp.data).lower()

    @pytest.mark.parametrize("raw", ["V12345678", "E-A123456", "J310123456"])
    def test_tax_id_valid_formats_accepted(self, api_client, business, raw) -> None:
        """Los tres tipos aceptan números dentro de su rango."""
        resp = api_client.post(
            self.URL,
            {"name": f"Cliente {raw}", "type": "cliente", "tax_id": raw},
        )
        assert resp.status_code == 201, resp.data

    def test_tax_id_unique_ignoring_format(self, api_client, business) -> None:
        """«v12345678» y «V-12345678» son la misma cédula: no se repite."""
        BusinessContact.objects.create(
            user=api_client.user,
            business=business,
            name="A",
            type="cliente",
            tax_id="V-12345678",
        )
        resp = api_client.post(
            self.URL,
            {"name": "B", "type": "cliente", "tax_id": "v12345678"},
        )
        assert resp.status_code == 400
        assert "cédula" in str(resp.data).lower()

    def test_search_by_tax_id_without_prefix(self, api_client, business) -> None:
        """La búsqueda encuentra por cédula con o sin prefijo."""
        BusinessContact.objects.create(
            user=api_client.user,
            business=business,
            name="Pedro",
            type="cliente",
            tax_id="V-12345678",
        )
        for term in ["12345678", "v12345678", "V-12345678", "12345"]:
            resp = api_client.get(f"{self.URL}?search={term}")
            assert resp.status_code == 200
            assert len(resp.data["results"]) == 1, term

    def test_tax_id_still_optional(self, api_client, business) -> None:
        """La cédula sigue siendo opcional para contactos sin ella."""
        first = api_client.post(
            self.URL, {"name": "Sin RIF 1", "type": "cliente"}
        )
        second = api_client.post(
            self.URL, {"name": "Sin RIF 2", "type": "cliente"}
        )
        assert first.status_code == 201
        assert second.status_code == 201
        assert first.data["tax_id"] == ""
