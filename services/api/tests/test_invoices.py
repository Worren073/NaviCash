"""tests — CRM: facturación y cuentas por cobrar."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from apps.business.services import create_business
from apps.crm.models import BusinessContact, Invoice, InvoicePayment
from apps.notifications.models import Notification
from apps.transactions.models import Transaction
from apps.wallets.models import Wallet
from factories import UserFactory


@pytest.mark.django_db
class TestInvoices:
    """Endpoints /api/business/invoices/."""

    URL = "/api/business/invoices/"

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
            payment_terms_days=15,
        )

    def _payload(self, contact, **overrides):
        data = {
            "contact": str(contact.id),
            "items": [
                {"description": "Producto 1", "quantity": "2", "unit_price": "100.00"},
                {"description": "Producto 2", "quantity": "1", "unit_price": "50.00"},
            ],
        }
        data.update(overrides)
        return data

    def test_create_invoice_enviada(self, api_client, business, contact) -> None:
        """POST crea una factura con número F-00001 y estado enviada."""
        resp = api_client.post(self.URL, self._payload(contact), format="json")
        assert resp.status_code == 201, resp.data
        assert resp.data["number"] == "F-00001"
        assert resp.data["status"] == "enviada"
        assert resp.data["subtotal"] == "250.00"
        assert resp.data["total"] == "250.00"
        assert resp.data["balance_due"] == "250.00"
        assert len(resp.data["items"]) == 2
        assert Invoice.objects.filter(user=api_client.user).count() == 1

    def test_invoice_numbering_sequential(self, api_client, business, contact) -> None:
        """Los números siguen el patrón F-00001, F-00002..."""
        for expected in ("F-00001", "F-00002", "F-00003"):
            resp = api_client.post(self.URL, self._payload(contact), format="json")
            assert resp.status_code == 201
            assert resp.data["number"] == expected

    def test_create_invoice_taxes_and_deadline(self, api_client, business, contact) -> None:
        """El impuesto se suma al total y el vencimiento usa los días del contacto."""
        resp = api_client.post(
            self.URL,
            self._payload(contact, tax_amount="12.50", issue_date="2026-10-01"),
            format="json",
        )
        assert resp.status_code == 201
        assert resp.data["tax_amount"] == "12.50"
        assert resp.data["total"] == "262.50"
        assert resp.data["due_date"] == "2026-10-16"

    def test_create_invoice_full_paid(self, api_client, business, contact) -> None:
        """paid_amount == total: factura pagada y el cobro acredita la billetera."""
        wallet = Wallet.objects.get(business=business)
        resp = api_client.post(
            self.URL, self._payload(contact, paid_amount="250.00"), format="json"
        )
        assert resp.status_code == 201, resp.data
        assert resp.data["status"] == "pagada"
        assert resp.data["amount_paid"] == "250.00"
        assert resp.data["balance_due"] == "0.00"
        wallet.refresh_from_db()
        assert wallet.saldo == Decimal("250.00")
        assert Transaction.objects.filter(
            user=api_client.user, tipo="cobro", wallet=wallet
        ).count() == 1
        assert InvoicePayment.objects.filter(invoice_id=resp.data["id"]).count() == 1

    def test_create_invoice_partial(self, api_client, business, contact) -> None:
        """paid_amount parcial: estado parcial y saldo pendiente correcto."""
        resp = api_client.post(
            self.URL, self._payload(contact, paid_amount="100.00"), format="json"
        )
        assert resp.status_code == 201
        assert resp.data["status"] == "parcial"
        assert resp.data["balance_due"] == "150.00"

    def test_paid_exceeds_total(self, api_client, business, contact) -> None:
        """El pago inicial no puede exceder el total."""
        resp = api_client.post(
            self.URL, self._payload(contact, paid_amount="999.00"), format="json"
        )
        assert resp.status_code == 400

    def test_requires_items(self, api_client, business, contact) -> None:
        """La factura debe tener al menos una línea."""
        resp = api_client.post(
            self.URL, {"contact": str(contact.id), "items": []}, format="json"
        )
        assert resp.status_code == 400
        errors = resp.data.get("errors", resp.data)
        assert "items" in errors

    def test_list_only_own(self, api_client, business, contact) -> None:
        """GET devuelve solo las facturas del usuario."""
        Invoice.objects.create(
            user=api_client.user,
            business=business,
            contact=contact,
            number="F-00001",
            issue_date=date.today(),
            due_date=date.today() + timedelta(days=15),
            status="enviada",
            subtotal=Decimal("10.00"),
            total=Decimal("10.00"),
            balance_due=Decimal("10.00"),
        )
        other = UserFactory()
        other_business = create_business(
            other, name="Otra", currency="USD", initial_capital=Decimal("0")
        )
        other_contact = BusinessContact.objects.create(
            user=other, business=other_business, name="Otro", type="cliente"
        )
        Invoice.objects.create(
            user=other,
            business=other_business,
            contact=other_contact,
            number="F-00001",
            issue_date=date.today(),
            due_date=date.today() + timedelta(days=15),
            status="enviada",
            subtotal=Decimal("99.00"),
            total=Decimal("99.00"),
            balance_due=Decimal("99.00"),
        )
        resp = api_client.get(self.URL)
        assert resp.status_code == 200
        assert len(resp.data["results"]) == 1
        assert resp.data["results"][0]["number"] == "F-00001"

    def test_pay_action(self, api_client, business, contact) -> None:
        """POST pay liquida la factura y notifica (invoice_paid)."""
        invoice = Invoice.objects.create(
            user=api_client.user,
            business=business,
            contact=contact,
            number="F-00001",
            issue_date=date.today(),
            due_date=date.today() + timedelta(days=15),
            status="enviada",
            subtotal=Decimal("250.00"),
            total=Decimal("250.00"),
            balance_due=Decimal("250.00"),
        )
        wallet = Wallet.objects.get(business=business)
        resp = api_client.post(f"{self.URL}{invoice.id}/pay/", {"amount": "250.00"})
        assert resp.status_code == 200
        assert resp.data["status"] == "pagada"
        assert resp.data["balance_due"] == "0.00"
        wallet.refresh_from_db()
        assert wallet.saldo == Decimal("250.00")
        assert Notification.objects.filter(
            user=api_client.user, kind="invoice_paid", scope="business"
        ).count() == 1

    def test_pay_partial(self, api_client, business, contact) -> None:
        """POST pay con monto parcial deja la factura en estado parcial."""
        invoice = Invoice.objects.create(
            user=api_client.user,
            business=business,
            contact=contact,
            number="F-00001",
            issue_date=date.today(),
            due_date=date.today() + timedelta(days=15),
            status="enviada",
            subtotal=Decimal("250.00"),
            total=Decimal("250.00"),
            balance_due=Decimal("250.00"),
        )
        resp = api_client.post(f"{self.URL}{invoice.id}/pay/", {"amount": "60.00"})
        assert resp.status_code == 200
        assert resp.data["status"] == "parcial"
        assert resp.data["amount_paid"] == "60.00"
        assert resp.data["balance_due"] == "190.00"

    def test_pay_over_balance(self, api_client, business, contact) -> None:
        """No se puede pagar más del saldo pendiente."""
        invoice = Invoice.objects.create(
            user=api_client.user,
            business=business,
            contact=contact,
            number="F-00001",
            issue_date=date.today(),
            due_date=date.today() + timedelta(days=15),
            status="enviada",
            subtotal=Decimal("250.00"),
            total=Decimal("250.00"),
            balance_due=Decimal("250.00"),
        )
        resp = api_client.post(f"{self.URL}{invoice.id}/pay/", {"amount": "999.00"})
        assert resp.status_code == 400

    def test_send_action(self, api_client, business, contact) -> None:
        """POST send publica la factura en borrador."""
        invoice = Invoice.objects.create(
            user=api_client.user,
            business=business,
            contact=contact,
            number="F-00001",
            issue_date=date.today(),
            due_date=date.today() + timedelta(days=15),
            status="borrador",
            subtotal=Decimal("10.00"),
            total=Decimal("10.00"),
            balance_due=Decimal("10.00"),
        )
        resp = api_client.post(f"{self.URL}{invoice.id}/send/")
        assert resp.status_code == 200
        assert resp.data["status"] == "enviada"

    def test_cancel_action(self, api_client, business, contact) -> None:
        """POST cancel anula la factura."""
        invoice = Invoice.objects.create(
            user=api_client.user,
            business=business,
            contact=contact,
            number="F-00001",
            issue_date=date.today(),
            due_date=date.today() + timedelta(days=15),
            status="enviada",
            subtotal=Decimal("10.00"),
            total=Decimal("10.00"),
            balance_due=Decimal("10.00"),
        )
        resp = api_client.post(f"{self.URL}{invoice.id}/cancel/")
        assert resp.status_code == 200
        assert resp.data["status"] == "anulada"

    def test_cannot_pay_annulled(self, api_client, business, contact) -> None:
        """No se puede pagar una factura anulada."""
        invoice = Invoice.objects.create(
            user=api_client.user,
            business=business,
            contact=contact,
            number="F-00001",
            issue_date=date.today(),
            due_date=date.today() + timedelta(days=15),
            status="anulada",
            subtotal=Decimal("10.00"),
            total=Decimal("10.00"),
            balance_due=Decimal("10.00"),
        )
        resp = api_client.post(f"{self.URL}{invoice.id}/pay/", {"amount": "10.00"})
        assert resp.status_code == 400

    def test_cannot_access_other_user(self, api_client, contact) -> None:
        """Un usuario no accede a facturas ajenas."""
        other = UserFactory()
        other_business = create_business(
            other, name="Otro", currency="USD", initial_capital=Decimal("0")
        )
        other_contact = BusinessContact.objects.create(
            user=other, business=other_business, name="Otro", type="cliente"
        )
        invoice = Invoice.objects.create(
            user=other,
            business=other_business,
            contact=other_contact,
            number="F-00001",
            issue_date=date.today(),
            due_date=date.today() + timedelta(days=15),
            status="enviada",
            subtotal=Decimal("10.00"),
            total=Decimal("10.00"),
            balance_due=Decimal("10.00"),
        )
        assert api_client.get(f"{self.URL}{invoice.id}/").status_code == 404
        assert (
            api_client.post(f"{self.URL}{invoice.id}/pay/", {"amount": "1"}).status_code
            == 404
        )

    def test_invoice_overdue_notification(self, api_client, business, contact) -> None:
        """El refresco de notificaciones detecta facturas vencidas."""
        invoice = Invoice.objects.create(
            user=api_client.user,
            business=business,
            contact=contact,
            number="F-00001",
            issue_date=date.today() - timedelta(days=30),
            due_date=date.today() - timedelta(days=15),
            status="enviada",
            subtotal=Decimal("250.00"),
            total=Decimal("250.00"),
            balance_due=Decimal("250.00"),
        )
        from apps.notifications.services import refresh_notifications

        result = refresh_notifications(api_client.user, scope="business")
        assert any(n.kind == "invoice_overdue" for n in result)
        invoice.refresh_from_db()
        assert invoice.status == "vencida"