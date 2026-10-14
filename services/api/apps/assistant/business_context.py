"""business_context — Contexto del NEGOCIO del usuario para el asistente Navi.

Es la puerta de entrada del LLM a los datos del módulo de negocios (CRM +
finanzas del negocio) cuando la vista activa es ``business``. Produce un dict
JSONizable, agregado y SIN datos personales: su saldo, flujo del mes, tablero
(P&L, aging, top clientes/proveedores, KPIs), inventario bajo y cartera abierta.

Reutiliza ``business.services.build_business_summary`` y
``build_business_analytics`` para no duplicar la lógica de agregación.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.utils import timezone

from apps.assistant.memory import memory_context
from apps.business.models import Business
from apps.business.services import build_business_analytics, build_business_summary
from apps.core.currency import round_money
from apps.crm.models import Invoice, Order, Product
from apps.rates.service import get_current_euro_rate, get_current_official_rate

#: Estados de factura que representan cartera por cobrar (abierta).
OPEN_INVOICE_STATUSES = ("enviada", "parcial", "vencida")

#: Máximo de filas por lista en el contexto (evita prompts gigantes).
_MAX_ROWS = 8


def build_business_context(user, today: date | None = None) -> dict:
    """Resumen agregado del negocio del usuario para el contexto de Navi.

    Args:
        user: usuario autenticado.
        today: fecha de corte (inyectable en tests; por defecto hoy local).

    Returns:
        Dict plano, JSON-friendly, con el estado del negocio. Si el usuario no
        tiene negocio, ``business`` es ``None`` y ``note`` es ``"no_business"``.
    """
    today = today or timezone.localdate()
    business = Business.objects.filter(user=user).select_related("wallet").first()

    if business is None:
        return {
            "view": "business",
            "business": None,
            "note": "no_business",
            "memoria": memory_context(user),
        }

    rate = get_current_official_rate()
    rate_value: "Decimal | None" = rate.effective_rate if rate else None
    euro = get_current_euro_rate()
    euro_value: "Decimal | None" = euro.effective_rate if euro else None

    summary = build_business_summary(business, today)
    analytics = build_business_analytics(business, months=6, today=today)

    recent = [
        {
            "tipo": t.tipo,
            "concepto": t.concepto,
            "monto": str(t.monto),
            "moneda": t.moneda,
            "fecha": (t.fecha_pagado or t.fecha).isoformat() if (t.fecha_pagado or t.fecha) else None,
        }
        for t in summary["recent"]
    ]

    low_stock = [
        {
            "name": p.name,
            "stock_quantity": str(p.stock_quantity),
            "unit": p.unit,
            "threshold": str(p.low_stock_threshold) if p.low_stock_threshold is not None else None,
        }
        for p in Product.objects.filter(business=business)
        if p.low_stock_threshold is not None and p.stock_quantity <= p.low_stock_threshold
    ][:_MAX_ROWS]

    open_invoices = _open_invoices(business, today)
    pending_orders = _pending_orders(business)
    inventory = _inventory(business)

    return {
        "view": "business",
        "business": {"name": business.name, "currency": business.currency},
        "rate": str(rate_value) if rate_value is not None else None,
        "euro_rate": str(euro_value) if euro_value is not None else None,
        "saldo": summary["saldo"],
        "currency": summary["currency"],
        "ingresos_mes": summary["ingresos_mes"],
        "egresos_mes": summary["egresos_mes"],
        "kpis": analytics["kpis"],
        "pnl": analytics["pnl"],
        "aging": analytics["aging"],
        "income_categories": analytics["incomeCategories"][:_MAX_ROWS],
        "expense_categories": analytics["expenseCategories"][:_MAX_ROWS],
        "top_clients": analytics["topClients"],
        "top_suppliers": analytics["topSuppliers"],
        "inventory": inventory,
        "low_stock": low_stock,
        "open_invoices": open_invoices,
        "pending_orders": pending_orders,
        "recent_transactions": recent,
        "memoria": memory_context(user),
    }


def _open_invoices(business: Business, today: date) -> dict:
    """Cartera por cobrar: total, vencido y las facturas abiertas más relevantes."""
    invoices = list(
        Invoice.objects.filter(
            business=business,
            status__in=OPEN_INVOICE_STATUSES,
            balance_due__gt=0,
        )
        .select_related("contact")
        .order_by("due_date")
    )
    by_currency = _sum_by_currency(invoices)
    overdue = [
        {
            "number": inv.number,
            "contact": inv.contact.name,
            "due_date": inv.due_date.isoformat(),
            "days_overdue": max(0, (today - inv.due_date).days),
            "balance_due": str(inv.balance_due),
            "currency": inv.currency,
        }
        for inv in invoices
        if inv.due_date < today
    ][:_MAX_ROWS]
    return {
        "count": len(invoices),
        "by_currency": by_currency,
        "top": [
            {
                "number": inv.number,
                "contact": inv.contact.name,
                "due_date": inv.due_date.isoformat(),
                "balance_due": str(inv.balance_due),
                "currency": inv.currency,
                "status": inv.status,
            }
            for inv in invoices[:_MAX_ROWS]
        ],
        "overdue": overdue,
    }


def _pending_orders(business: Business) -> dict:
    """Cartera por pagar: pedidos con saldo pendiente (excluye anulados)."""
    orders = list(
        Order.objects.filter(business=business, balance_due__gt=0)
        .exclude(status="anulado")
        .select_related("contact")
        .order_by("order_date")
    )
    return {
        "count": len(orders),
        "by_currency": _sum_by_currency(orders),
        "top": [
            {
                "number": order.number,
                "contact": order.contact.name,
                "order_date": order.order_date.isoformat(),
                "balance_due": str(order.balance_due),
                "currency": order.currency,
                "status": order.status,
            }
            for order in orders[:_MAX_ROWS]
        ],
    }


def _sum_by_currency(rows: list) -> dict[str, str]:
    """Suma ``balance_due`` agrupada por moneda (sin mezclar divisas)."""
    totals: dict[str, Decimal] = {}
    for row in rows:
        totals[row.currency] = totals.get(row.currency, Decimal("0")) + row.balance_due
    return {currency: str(round_money(total)) for currency, total in totals.items()}


def _inventory(business: Business) -> dict:
    """Resumen del inventario: número de productos, valor y top por valor."""
    products = list(Product.objects.filter(business=business, is_active=True))
    lines = []
    total_value = Decimal("0")
    for p in products:
        cost = p.cost_price or Decimal("0")
        value = round_money(p.stock_quantity * cost)
        total_value += value
        lines.append(
            {
                "name": p.name,
                "stock_quantity": str(p.stock_quantity),
                "unit": p.unit,
                "value": str(value),
            }
        )
    lines.sort(key=lambda item: Decimal(item["value"]), reverse=True)
    return {
        "product_count": len(products),
        "total_value": str(round_money(total_value)),
        "top": lines[:_MAX_ROWS],
    }
