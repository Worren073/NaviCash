"""tests — Navi en la vista de NEGOCIO: contexto, fallback, tools y endpoint."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.assistant.business_context import build_business_context
from apps.assistant.context import build_context
from apps.assistant.intent_rules import answer_deterministic
from apps.assistant.providers import (
    SYSTEM_PROMPT_BUSINESS_WITH_TOOLS,
    _system_prompt,
)
from apps.assistant.tools import execute_tool
from apps.business.models import Business
from apps.business.services import create_business
from apps.crm.models import BusinessContact, Invoice, Order, Product
from apps.rates.models import ExchangeRate


def _seed_rate() -> None:
    """Siembra la tasa oficial (100 VES/USD) para las conversiones."""
    if not ExchangeRate.objects.filter(source="oficial").exists():
        ExchangeRate.objects.create(
            source="oficial",
            currency="VES",
            promedio=Decimal("100.00"),
            rate_date=timezone.now(),
        )


def _make_business(user, *, capital: str = "0.00") -> Business:
    """Crea el negocio del usuario con su billetera."""
    return create_business(
        user, name="Mi Bodega", currency="USD", initial_capital=Decimal(capital)
    )


@pytest.mark.django_db
class TestBusinessContext:
    """build_context(view="business") produce el estado del negocio."""

    def test_without_business_marks_no_business(self, api_client) -> None:
        """Sin negocio: business=None, note="no_business" y view business."""
        context = build_context(api_client.user, view="business")
        assert context["view"] == "business"
        assert context["business"] is None
        assert context["note"] == "no_business"

    def test_personal_context_is_marked(self, api_client) -> None:
        """La vista personal se marca como tal."""
        context = build_context(api_client.user)
        assert context["view"] == "personal"

    def test_includes_business_and_never_personal(self, api_client) -> None:
        """El contexto de negocio incluye solo datos del negocio."""
        _seed_rate()
        business = _make_business(api_client.user, capital="500.00")
        context = build_context(api_client.user, view="business")

        assert context["view"] == "business"
        assert context["business"]["name"] == "Mi Bodega"
        assert context["currency"] == "USD"
        assert Decimal(context["saldo"]) == Decimal("500.00")
        # No filtra datos personales (claves del contexto personal).
        assert "total_balance_usd" not in context
        assert "goals" not in context
        assert business.wallet.saldo == Decimal("500.00")

    def test_includes_open_invoices_low_stock_and_orders(self, api_client) -> None:
        """Cartera por cobrar, stock bajo y pedidos pendientes del negocio."""
        _seed_rate()
        business = _make_business(api_client.user)
        contact = BusinessContact.objects.create(
            user=api_client.user, business=business, name="Cliente Uno", type="cliente"
        )
        # Factura abierta y vencida (por cobrar).
        Invoice.objects.create(
            user=api_client.user,
            business=business,
            contact=contact,
            number="F-001",
            issue_date=date.today() - timedelta(days=40),
            due_date=date.today() - timedelta(days=10),
            status="enviada",
            subtotal=Decimal("100.00"),
            total=Decimal("100.00"),
            balance_due=Decimal("100.00"),
        )
        # Producto con stock bajo.
        Product.objects.create(
            user=api_client.user,
            business=business,
            name="Harina",
            unit="kg",
            unit_price=Decimal("2.00"),
            cost_price=Decimal("1.00"),
            stock_quantity=Decimal("1.00"),
            low_stock_threshold=Decimal("5.00"),
        )
        # Pedido con saldo pendiente.
        Order.objects.create(
            user=api_client.user,
            business=business,
            contact=contact,
            number="P-001",
            order_date=date.today(),
            subtotal=Decimal("50.00"),
            total=Decimal("50.00"),
            balance_due=Decimal("50.00"),
        )
        context = build_business_context(api_client.user)

        assert context["open_invoices"]["count"] == 1
        assert context["open_invoices"]["by_currency"]["USD"] == "100.00"
        assert context["open_invoices"]["overdue"][0]["number"] == "F-001"
        assert context["low_stock"][0]["name"] == "Harina"
        assert context["pending_orders"]["count"] == 1
        assert context["pending_orders"]["by_currency"]["USD"] == "50.00"
        assert context["inventory"]["product_count"] == 1


@pytest.mark.django_db
class TestBusinessDeterministicFallback:
    """Reglas de negocio del fallback determinista (sin red)."""

    def test_no_business_guides_to_create(self, api_client) -> None:
        """Sin negocio, Navi guía a crearlo."""
        context = build_context(api_client.user, view="business")
        resp = answer_deterministic(context, "cuanto tengo?")
        assert "negocio creado" in resp.lower() or "no tienes un negocio" in resp.lower()

    def test_balance_intent(self, api_client) -> None:
        """«¿Cuánto tengo?» responde con el saldo del negocio."""
        _seed_rate()
        _make_business(api_client.user, capital="300.00")
        context = build_context(api_client.user, view="business")
        resp = answer_deterministic(context, "cuanto tengo en mi negocio?")
        assert "300.00" in resp
        assert "USD" in resp

    def test_receivables_intent(self, api_client) -> None:
        """«¿Qué me deben?» responde la cartera por cobrar."""
        _seed_rate()
        business = _make_business(api_client.user)
        contact = BusinessContact.objects.create(
            user=api_client.user, business=business, name="C", type="cliente"
        )
        Invoice.objects.create(
            user=api_client.user,
            business=business,
            contact=contact,
            number="F-002",
            issue_date=date.today(),
            due_date=date.today(),
            status="enviada",
            subtotal=Decimal("80.00"),
            total=Decimal("80.00"),
            balance_due=Decimal("80.00"),
        )
        context = build_context(api_client.user, view="business")
        resp = answer_deterministic(context, "cuanto me deben?")
        assert "80.00" in resp

    def test_payables_intent(self, api_client) -> None:
        """«¿Cuánto debo?» responde los pedidos pendientes."""
        _seed_rate()
        business = _make_business(api_client.user)
        contact = BusinessContact.objects.create(
            user=api_client.user, business=business, name="P", type="proveedor"
        )
        Order.objects.create(
            user=api_client.user,
            business=business,
            contact=contact,
            number="P-002",
            order_date=date.today(),
            subtotal=Decimal("30.00"),
            total=Decimal("30.00"),
            balance_due=Decimal("30.00"),
        )
        context = build_context(api_client.user, view="business")
        resp = answer_deterministic(context, "cuanto debo a mis proveedores?")
        assert "30.00" in resp

    def test_inventory_intent(self, api_client) -> None:
        """«Inventario» responde valor y stock bajo."""
        _seed_rate()
        business = _make_business(api_client.user)
        Product.objects.create(
            user=api_client.user,
            business=business,
            name="Arroz",
            unit="kg",
            unit_price=Decimal("2.00"),
            cost_price=Decimal("1.00"),
            stock_quantity=Decimal("0.00"),
            low_stock_threshold=Decimal("3.00"),
        )
        context = build_context(api_client.user, view="business")
        resp = answer_deterministic(context, "como esta mi inventario?")
        assert "Arroz" in resp


@pytest.mark.django_db
class TestBusinessTools:
    """Las tools de negocio leen del contexto (solo lectura)."""

    def test_receivables_tool(self, api_client) -> None:
        """get_receivables devuelve KPIs y facturas abiertas."""
        _seed_rate()
        business = _make_business(api_client.user)
        contact = BusinessContact.objects.create(
            user=api_client.user, business=business, name="C", type="cliente"
        )
        Invoice.objects.create(
            user=api_client.user,
            business=business,
            contact=contact,
            number="F-003",
            issue_date=date.today(),
            due_date=date.today(),
            status="enviada",
            subtotal=Decimal("40.00"),
            total=Decimal("40.00"),
            balance_due=Decimal("40.00"),
        )
        context = build_context(api_client.user, view="business")
        result = execute_tool("get_receivables", {}, context)
        assert result["open_invoices"]["count"] == 1
        assert result["receivable"] is not None

    def test_business_tool_without_business_errors(self, api_client) -> None:
        """Sin negocio, las tools de negocio devuelven error legible."""
        context = build_context(api_client.user, view="business")
        result = execute_tool("get_inventory", {}, context)
        assert result["error"] == "no_business"

    def test_inventory_tool(self, api_client) -> None:
        """get_inventory devuelve el resumen del inventario."""
        _seed_rate()
        business = _make_business(api_client.user)
        Product.objects.create(
            user=api_client.user,
            business=business,
            name="Café",
            unit="kg",
            unit_price=Decimal("10.00"),
            cost_price=Decimal("5.00"),
            stock_quantity=Decimal("4.00"),
        )
        context = build_context(api_client.user, view="business")
        result = execute_tool("get_inventory", {}, context)
        assert result["inventory"]["product_count"] == 1


@pytest.mark.django_db
class TestBusinessPromptAndEndpoint:
    """Selección de prompt por vista y endpoint con view=business."""

    def test_business_prompt_selected(self, api_client) -> None:
        """El provider usa el prompt de negocio con tools."""
        context = build_context(api_client.user, view="business")
        assert _system_prompt(context, with_tools=True) == SYSTEM_PROMPT_BUSINESS_WITH_TOOLS

    def test_endpoint_business_view(self, api_client) -> None:
        """POST con view=business responde en scope de negocio."""
        _seed_rate()
        _make_business(api_client.user, capital="150.00")
        resp = api_client.post(
            "/api/assistant/messages",
            {"message": "cuanto tengo?", "view": "business"},
            format="json",
        )
        assert resp.status_code == 200
        assert resp.data["view"] == "business"
        assert "negocio" in resp.data["text"].lower()

    def test_endpoint_defaults_to_personal(self, api_client) -> None:
        """Sin view, el turno es personal."""
        resp = api_client.post(
            "/api/assistant/messages", {"message": "cuanto tengo?"}, format="json"
        )
        assert resp.status_code == 200
        assert resp.data["view"] == "personal"

    def test_message_override_promotes_to_business(self, api_client) -> None:
        """En vista personal, «factura» con negocio promueve a negocio."""
        _seed_rate()
        _make_business(api_client.user)
        context = build_context(api_client.user, view="business")
        assert context["view"] == "business"
        # El endpoint debe resolver la vista por el mensaje.
        resp = api_client.post(
            "/api/assistant/messages",
            {"message": "muestrame mi inventario del negocio", "view": "personal"},
            format="json",
        )
        assert resp.status_code == 200
        assert resp.data["view"] == "business"

    def test_invalid_view_rejected(self, api_client) -> None:
        """Una vista inválida devuelve 400."""
        resp = api_client.post(
            "/api/assistant/messages",
            {"message": "hola", "view": "otra"},
            format="json",
        )
        assert resp.status_code == 400
