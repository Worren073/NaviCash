"""context — Construcción del contexto del usuario para el asistente Navi.

Es la ÚNICA puerta de entrada del modelo LLM a los datos del usuario. Produce
un dict JSONizable con el estado agregado de su dominio financiero, sin exponer
credenciales, tokens, emails de contacto ni datos de otros usuarios.

Reutiliza los servicios existentes (overview, savings, subscriptions) para no
duplicar lógica de agregación.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.utils import timezone

from apps.core.currency import convert_to_usd, round_money
from apps.overview.services import build_summary
from apps.rates.service import get_current_official_rate
from apps.savings.models import SavingsGoal
from apps.subscriptions.models import Subscription
from apps.transactions.models import Transaction


def build_context(user, today: date | None = None) -> dict:
    """Resumen agregado del dominio del usuario para el contexto del asistente.

    Args:
        user: usuario autenticado.
        today: fecha de corte (inyectable en tests; por defecto hoy local).

    Returns:
        Dict plano, JSON-friendly, con el estado financiero del usuario.
    """
    today = today or timezone.localdate()
    summary = build_summary(user, today)

    rate = get_current_official_rate()
    rate_value: "Decimal | None" = rate.effective_rate if rate else None

    # Ingresos y gastos del mes actual (USD, desde montos congelados).
    month_start = today.replace(day=1)
    month_range = (
        Transaction.objects.filter(
            user=user,
            estado="pagado",
            fecha__gte=month_start,
            fecha__lte=today,
        ).exclude(tipo="transferencia")
    )
    income, expenses = Decimal("0"), Decimal("0")
    for t in month_range:
        usd = t.monto_usd
        if usd is None:
            continue
        if t.tipo == "cobro":
            income += usd
        elif t.tipo == "pago":
            expenses += usd
    fin_month = {
        "income": str(round_money(income)),
        "expenses": str(round_money(expenses)),
        "net": str(round_money(income - expenses)),
    }

    # Metas con avance (solo datos públicos del propio usuario).
    goals = [
        {
            "name": g.name,
            "progress_percent": str(g.progress_percent),
            "target_amount": str(g.target_amount),
            "currency": g.currency,
            "total_contributed": str(g.total_contributed),
        }
        for g in SavingsGoal.objects.filter(user=user)
    ]

    # Mensualidades: nombre + estado + días restantes.
    subscriptions = [
        {
            "name": s.name,
            "status": s.status,
            "days_remaining": s.days_remaining,
            "days_total": s.days_total,
        }
        for s in Subscription.objects.filter(user=user)
    ]

    # Recientes pagadas (sin exponer notas ni contactos sensibles).
    recent = list(
        Transaction.objects.filter(user=user, estado="pagado")
        .select_related("wallet")
        .exclude(tipo="transferencia")
        .order_by("-fecha_pagado", "-fecha")[:10]
    )
    recent_items = [
        {
            "tipo": t.tipo,
            "concepto": t.concepto,
            "monto": str(t.monto),
            "moneda": t.moneda,
            "wallet": t.wallet.name if t.wallet else None,
            "fecha": t.fecha.isoformat(),
        }
        for t in recent
    ]

    # Bancos/cuentas con su saldo en moneda local y en USD cuando aplica.
    wallets = [
        {
            "name": w.name,
            "currency": w.currency,
            "saldo": str(w.saldo),
            "usd_value": str(w.usd_value) if getattr(w, "usd_value", None) is not None else None,
            "tipo": w.tipo,
        }
        for w in summary["wallets"]
    ]

    return {
        "base_currency": user.base_currency,
        "rate": str(rate_value) if rate_value is not None else None,
        "total_balance_usd": str(summary["total_balance_usd"]),
        "total_balance_ves": str(summary["total_balance_ves"]) if summary["total_balance_ves"] is not None else None,
        "to_receive": str(summary["to_receive"]),
        "to_pay": str(summary["to_pay"]),
        "overdue": str(summary["overdue"]),
        "upcoming": [
            {
                "concepto": tx.concepto,
                "tipo": tx.tipo,
                "monto": str(tx.monto),
                "moneda": tx.moneda,
                "fecha_vencimiento": tx.fecha_vencimiento.isoformat(),
            }
            for tx in summary["upcoming"]
        ],
        "wallets": wallets,
        "savings_total_usd": _savings_total(wallets, rate_value),
        "goals": goals,
        "subscriptions": subscriptions,
        "fin_month": fin_month,
        "recent_transactions": recent_items,
    }


def _savings_total(wallets: list[dict], rate_value: "Decimal | None") -> str:
    """Suma de los saldos de cuentas ``saving`` en USD (si hay tasa)."""
    total = Decimal("0")
    for w in wallets:
        if w.get("tipo") != "saving":
            continue
        if w["currency"] == "USD":
            total += Decimal(w["saldo"])
        elif w["currency"] == "VES" and rate_value and rate_value > 0:
            total += convert_to_usd(w["saldo"], "VES", rate_value)
    return str(round_money(total))