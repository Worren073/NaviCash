"""services — Lógica de negocio del módulo Business.

``create_business`` es la ÚNICA puerta de entrada para crear un negocio: crea
su billetera (tipo ``business``) y acredita el capital inicial vía
``adjust_balance`` (auditoría ``capital_inicial``, ADR-08). El resumen del
dashboard agrega SIEMPRE solo la billetera del negocio: nunca ve lo personal.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from django.db import transaction
from django.db.models import F, Q, Sum
from django.db.models.functions import Coalesce, TruncMonth
from django.utils import timezone

from apps.business.models import Business
from apps.core.currency import round_money, usd_to_currency
from apps.core.exceptions import BusinessRuleError
from apps.crm.models import Invoice, InvoicePayment, Order, OrderPayment, Product
from apps.rates.service import get_current_official_rate
from apps.transactions.models import Transaction
from apps.wallets.models import Wallet
from apps.wallets.services import adjust_balance


@transaction.atomic
def create_business(user, *, name: str, currency: str, initial_capital: Decimal) -> Business:
    """Crea el negocio del usuario y su cuenta (billetera de negocio).

    El capital inicial es EXTERNO (aportado en efectivo por el dueño, no sale
    de billeteras personales): se acredita a la cuenta del negocio al nacer.

    Args:
        user: dueño del negocio.
        name: nombre visible (único por usuario).
        currency: moneda del negocio (ISO 4217).
        initial_capital: capital inicial (>= 0) en la moneda del negocio.

    Returns:
        El ``Business`` creado con su billetera.

    Raises:
        BusinessRuleError: si ya existe un negocio, el nombre está vacío o el
            capital inicial es negativo.
    """
    if Business.objects.filter(user=user).exists():
        raise BusinessRuleError("Ya tienes un negocio creado.")

    name = (name or "").strip()
    if not name:
        raise BusinessRuleError("El nombre del negocio no puede estar vacío.")

    initial_capital = round_money(initial_capital)
    if initial_capital < 0:
        raise BusinessRuleError("El capital inicial no puede ser negativo.")

    wallet = Wallet.objects.create(
        user=user,
        name=name,
        currency=currency,
        tipo="business",
        color="#0891b2",
    )
    business = Business.objects.create(user=user, name=name, currency=currency)
    wallet.business = business
    wallet.save(update_fields=["business"])
    if initial_capital > 0:
        adjust_balance(wallet, initial_capital, reason="capital_inicial")
    return business


def build_business_summary(business: Business, today: "date | None" = None) -> dict:
    """Agrega las métricas del dashboard del negocio.

    Todas las operaciones se acotan a la billetera del negocio: lo personal
    jamás contamina estos totales.

    Args:
        business: negocio (con su ``wallet`` cargada).
        today: fecha de corte (por defecto, la local actual).

    Returns:
        Dict con ``saldo``, ``currency``, ``ingresos_mes``, ``egresos_mes``
        y ``recent`` (operaciones pagadas recientes, para el listado).
    """
    today = today or timezone.localdate()
    wallet = business.wallet
    base = business.currency
    rate = get_current_official_rate()
    rate_value: "Decimal | None" = rate.effective_rate if rate else None

    month_start = today.replace(day=1)
    month_end = date(today.year + (today.month // 12), today.month % 12 + 1, 1)
    totals = (
        Transaction.objects.filter(
            wallet=wallet,
            estado="pagado",
            fecha_pagado__date__gte=month_start,
            fecha_pagado__date__lt=month_end,
        ).aggregate(
            ingresos=Sum("monto_usd", filter=Q(tipo="cobro")),
            egresos=Sum("monto_usd", filter=Q(tipo="pago")),
        )
    )

    recent = list(
        Transaction.objects.filter(wallet=wallet, estado="pagado")
        .select_related("category", "contact")
        .order_by("-fecha_pagado", "-fecha")[:6]
    )

    return {
        "saldo": str(round_money(wallet.saldo)),
        "currency": base,
        "ingresos_mes": str(
            round_money(
                usd_to_currency(totals["ingresos"] or Decimal("0.00"), base, rate_value or Decimal("1"))
            )
        ),
        "egresos_mes": str(
            round_money(
                usd_to_currency(totals["egresos"] or Decimal("0.00"), base, rate_value or Decimal("1"))
            )
        ),
        "recent": recent,
    }


OPEN_INVOICE_STATUSES = ("enviada", "parcial", "vencida")


def _first_day_months_back(today: date, offset_months: int) -> date:
    """Primer día del mes que queda ``offset_months`` meses atrás de *today*."""
    total = today.year * 12 + (today.month - 1) - offset_months
    return date(total // 12, total % 12 + 1, 1)


def _month_series(today: date, months: int) -> list[date]:
    """Serie de primeros de mes desde ``months`` meses atrás hasta el actual."""
    end = date(today.year, today.month, 1)
    start = _first_day_months_back(today, months - 1)
    series = []
    cursor = start
    while cursor <= end:
        series.append(cursor)
        cursor = date(cursor.year + (cursor.month // 12), cursor.month % 12 + 1, 1)
    return series


def _to_business_amount(amount: Decimal, currency: str, base: str, rate_value: Decimal) -> Decimal:
    """Convierte un monto a la moneda del negocio (v1: solo desde USD).

    Un monto ya en la moneda del negocio se devuelve tal cual; uno en USD se
    convierte con la tasa oficial vigente; cualquier otra moneda se usa a su
    valor nominal (no se mezcla con el resto del tablero sin tasa conjunta).
    """
    if currency == base:
        return amount
    if currency == "USD":
        return usd_to_currency(amount, base, rate_value or Decimal("1"))
    return amount


def _month_key(value: "date | datetime") -> date:
    """Normaliza el primer día del mes que devuelve ``TruncMonth`` a ``date``."""
    return value.date() if isinstance(value, datetime) else value


def build_business_analytics(business: Business, months: int = 12, today: "date | None" = None) -> dict:
    """Agrega las analíticas del negocio para el tablero financiero.

    Todo se acota a la billetera del negocio (operaciones pagadas) y a sus
    facturas/pedidos/productos (el CRM). Las series con ``monto_usd`` se
    convierten a la moneda del negocio con la tasa oficial vigente, igual que
    ``build_business_summary``.

    Args:
        business: negocio (con su ``wallet`` cargada).
        months: ventana de la serie P&L (3-24; el llamador ya lo clampea).
        today: fecha de corte (por defecto, la local actual).

    Returns:
        Dict con ``currency``, ``months``, ``pnl``, ``incomeCategories``,
        ``expenseCategories``, ``aging``, ``topClients``, ``topSuppliers`` y
        ``kpis``. Los valores monetarios son números (float) redondeados y
        listos para graficar; las fechas usan formato ``YYYY-MM``.
    """
    today = today or timezone.localdate()
    wallet = business.wallet
    base = business.currency
    rate = get_current_official_rate()
    rate_value: "Decimal | None" = rate.effective_rate if rate else None
    one = rate_value or Decimal("1")

    cutoff = _first_day_months_back(today, months - 1)
    series = _month_series(today, months)

    paid = Transaction.objects.filter(
        wallet=wallet, estado="pagado", tipo__in=["cobro", "pago"],
        fecha_pagado__date__gte=cutoff,
    )
    rows = (
        paid.annotate(month=TruncMonth("fecha_pagado"))
        .values("month", "tipo")
        .annotate(total=Sum("monto_usd"))
    )
    by_month = {(_month_key(row["month"]), row["tipo"]): row["total"] or Decimal("0.00") for row in rows}

    pnl = []
    income_total = Decimal("0.00")
    expense_total = Decimal("0.00")
    for m in series:
        income = usd_to_currency(by_month.get((m, "cobro"), Decimal("0.00")), base, one)
        expense = usd_to_currency(by_month.get((m, "pago"), Decimal("0.00")), base, one)
        income_total += income
        expense_total += expense
        pnl.append(
            {
                "month": m.strftime("%Y-%m"),
                "income": round(float(income), 2),
                "expense": round(float(expense), 2),
                "net": round(float(income - expense), 2),
            }
        )

    def _categories(kind: str) -> list[dict]:
        grouped = (
            Transaction.objects.filter(
                wallet=wallet, estado="pagado", tipo=kind, fecha_pagado__date__gte=cutoff
            )
            .values("category__name")
            .annotate(total=Sum("monto_usd"))
            .order_by("-total")
        )
        return [
            {
                "label": row["category__name"] or "Sin categoría",
                "value": round(float(usd_to_currency(row["total"] or Decimal("0.00"), base, one)), 2),
            }
            for row in grouped
        ]

    open_invoices = list(
        Invoice.objects.filter(
            business=business, status__in=OPEN_INVOICE_STATUSES, balance_due__gt=0
        )
    )
    aging = {"0_30": Decimal("0.00"), "31_60": Decimal("0.00"), "61_90": Decimal("0.00"), "90": Decimal("0.00")}
    receivable = Decimal("0.00")
    overdue = Decimal("0.00")
    for inv in open_invoices:
        value = _to_business_amount(inv.balance_due, inv.currency, base, one)
        receivable += value
        days = max(0, (today - inv.due_date).days)
        if days <= 30:
            aging["0_30"] += value
        elif days <= 60:
            aging["31_60"] += value
        elif days <= 90:
            aging["61_90"] += value
        else:
            aging["90"] += value
        if days > 0:
            overdue += value

    payable = Decimal("0.00")
    for order in Order.objects.filter(business=business, balance_due__gt=0).exclude(status="anulado"):
        payable += _to_business_amount(order.balance_due, order.currency, base, one)

    inventory_value = (
        Product.objects.filter(business=business)
        .annotate(
            line_value=F("stock_quantity") * Coalesce(F("cost_price"), Decimal("0.00"))
        )
        .aggregate(total=Sum("line_value"))["total"]
        or Decimal("0.00")
    )

    def _top_sources(qs, name_path: str, currency_path: str) -> list[dict]:
        """Top por contacto a partir de pagos (cliente/proveedor) en la ventana."""
        grouped = (
            qs.annotate(_name=F(name_path), _currency=F(currency_path))
            .values("_name", "_currency")
            .annotate(total=Sum("amount"))
        )
        merged: dict[str, Decimal] = {}
        for row in grouped:
            total = _to_business_amount(
                row["total"] or Decimal("0.00"), row["_currency"] or base, base, one
            )
            name = row["_name"] or "—"
            merged[name] = merged.get(name, Decimal("0.00")) + total
        top = sorted(merged.items(), key=lambda item: item[1], reverse=True)[:5]
        return [{"label": name, "value": round(float(total), 2)} for name, total in top]

    top_clients = _top_sources(
        InvoicePayment.objects.filter(
            invoice__business=business, paid_at__date__gte=cutoff
        ),
        "invoice__contact__name",
        "invoice__currency",
    )
    top_suppliers = _top_sources(
        OrderPayment.objects.filter(order__business=business, paid_at__date__gte=cutoff),
        "order__contact__name",
        "order__currency",
    )

    margin_pct = round(float((income_total - expense_total) / income_total * 100), 1) if income_total > 0 else None

    return {
        "currency": base,
        "months": months,
        "pnl": pnl,
        "incomeCategories": _categories("cobro"),
        "expenseCategories": _categories("pago"),
        "aging": [
            {"bucket": key, "value": round(float(value), 2)} for key, value in aging.items()
        ],
        "topClients": top_clients,
        "topSuppliers": top_suppliers,
        "kpis": {
            "incomePeriod": round(float(income_total), 2),
            "expensePeriod": round(float(expense_total), 2),
            "marginPct": margin_pct,
            "receivable": round(float(receivable), 2),
            "payable": round(float(payable), 2),
            "overdue": round(float(overdue), 2),
            "inventoryValue": round(float(inventory_value), 2),
        },
    }