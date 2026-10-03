"""tests — CRM: pipeline de cobranza (seguimientos de facturas)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from apps.business.services import create_business
from apps.crm.models import BusinessContact, CollectionFollowUp
from factories import UserFactory


@pytest.mark.django_db
class TestCollectionFollowUp:
    """Endpoints /api/business/follow-ups/."""

    URL = "/api/business/follow-ups/"

    @pytest.fixture
    def business(self, api_client):
        return create_business(
            api_client.user, name="Tienda Demo", currency="USD", initial_capital=Decimal("0")
        )

    @pytest.fixture
    def contact(self, api_client, business):
        return BusinessContact.objects.create(
            user=api_client.user,
            business=business,
            name="Cliente A",
            type="cliente",
        )

    def _invoice(self, api_client, contact, **overrides):
        payload = {
            "contact": str(contact.id),
            "items": [
                {"description": "Producto 1", "quantity": "1", "unit_price": "100.00"},
            ],
        }
        payload.update(overrides)
        resp = api_client.post("/api/business/invoices/", payload, format="json")
        assert resp.status_code == 201, resp.data
        return resp.data

    def _follow_up(self, api_client, invoice_id, **overrides):
        payload = {
            "invoice": str(invoice_id),
            "channel": "llamada",
            "outcome": "sin_respuesta",
        }
        payload.update(overrides)
        return api_client.post(self.URL, payload, format="json")

    def test_create_follow_up(self, api_client, business, contact) -> None:
        """POST crea un seguimiento asociado al usuario."""
        invoice = self._invoice(api_client, contact)
        resp = self._follow_up(
            api_client,
            invoice["id"],
            channel="whatsapp",
            outcome="promesa_pago",
            promised_date="2026-10-10",
            notes="Me llama el lunes",
        )
        assert resp.status_code == 201, resp.data
        assert resp.data["channel"] == "whatsapp"
        assert resp.data["outcome"] == "promesa_pago"
        assert resp.data["promised_date"] == "2026-10-10"
        assert resp.data["notes"] == "Me llama el lunes"
        assert CollectionFollowUp.objects.filter(user=api_client.user).count() == 1

    def test_promise_requires_date(self, api_client, business, contact) -> None:
        """outcome promesa_pago exige fecha comprometida."""
        invoice = self._invoice(api_client, contact)
        resp = self._follow_up(api_client, invoice["id"], outcome="promesa_pago")
        assert resp.status_code == 400
        assert "promised_date" in resp.data["errors"]

    def test_list_filtered_by_invoice(self, api_client, business, contact) -> None:
        """GET ?invoice devuelve solo los seguimientos de esa factura."""
        inv_1 = self._invoice(api_client, contact)
        inv_2 = self._invoice(api_client, contact)
        self._follow_up(api_client, inv_1["id"])
        self._follow_up(api_client, inv_2["id"])

        resp = api_client.get(f"{self.URL}?invoice={inv_1['id']}")
        assert resp.status_code == 200
        assert len(resp.data["results"]) == 1
        assert str(resp.data["results"][0]["invoice"]) == inv_1["id"]

    def test_cannot_follow_up_other_users_invoice(self, api_client, business, contact) -> None:
        """Un usuario no puede registrar seguimientos sobre facturas ajenas."""
        other = UserFactory()
        other_business = create_business(
            other, name="Otro", currency="USD", initial_capital=Decimal("0")
        )
        other_contact = BusinessContact.objects.create(
            user=other, business=other_business, name="Cliente B", type="cliente"
        )
        from apps.crm.services import create_invoice

        other_invoice = create_invoice(
            other,
            other_business,
            other_contact,
            [{"description": "X", "quantity": "1", "unit_price": "10.00"}],
        )

        resp = self._follow_up(api_client, other_invoice.id)
        assert resp.status_code == 400

    def test_delete_follow_up(self, api_client, business, contact) -> None:
        """DELETE elimina el seguimiento (corrección de errores)."""
        invoice = self._invoice(api_client, contact)
        created = self._follow_up(api_client, invoice["id"])
        assert created.status_code == 201
        resp = api_client.delete(f"{self.URL}{created.data['id']}/")
        assert resp.status_code == 204
        assert CollectionFollowUp.objects.filter(user=api_client.user).count() == 0

    def test_cannot_update_follow_up(self, api_client, business, contact) -> None:
        """PATCH no está habilitado: los registros se borran y re-crean."""
        invoice = self._invoice(api_client, contact)
        created = self._follow_up(api_client, invoice["id"])
        resp = api_client.patch(
            f"{self.URL}{created.data['id']}/", {"outcome": "pago_realizado"}
        )
        assert resp.status_code == 405

    def test_invoice_serializer_includes_latest_follow_up(
        self, api_client, business, contact
    ) -> None:
        """El detalle de factura expone el seguimiento más reciente."""
        invoice = self._invoice(api_client, contact)
        self._follow_up(api_client, invoice["id"], outcome="sin_respuesta")
        latest = self._follow_up(
            api_client,
            invoice["id"],
            outcome="promesa_pago",
            promised_date=str(date(2026, 10, 15)),
        )
        assert latest.status_code == 201

        resp = api_client.get(f"/api/business/invoices/{invoice['id']}/")
        assert resp.status_code == 200
        latest_data = resp.data["latest_follow_up"]
        assert latest_data is not None
        assert latest_data["outcome"] == "promesa_pago"
        assert latest_data["promised_date"] == "2026-10-15"