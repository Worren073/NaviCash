"""services — Lógica de negocio del módulo Business.

``create_business`` es la ÚNICA puerta de entrada para crear un negocio: crea
sus DOS billeteras (tipo ``business``: principal en la moneda base y secundaria
en la otra) y acredita el capital inicial a la principal vía
``adjust_balance`` (auditoría ``capital_inicial``, ADR-08). El resumen del
dashboard agrega SIEMPRE solo las billeteras del negocio: nunca ve lo personal.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import F, Q, Sum
from django.db.models.functions import Coalesce, TruncDate, TruncMonth
from django.utils import timezone

from apps.business.models import Business
from apps.core.currency import (
    BUSINESS_CURRENCY_CODES,
    convert_to_usd,
    counterpart_currency,
    round_money,
    usd_to_currency,
)
from apps.core.exceptions import BusinessRuleError
from apps.crm.models import Invoice, InvoicePayment, Order, OrderPayment, Product
from apps.rates.service import get_current_official_rate
from apps.transactions.models import Transaction
from apps.wallets.models import Wallet
from apps.wallets.services import adjust_balance


@transaction.atomic
def create_business(user, *, name: str, currency: str, initial_capital: Decimal) -> Business:
    """Crea el negocio del usuario y sus DOS cuentas (billeteras de negocio).

    Se crean dos billeteras tipo ``business``: la ``primary`` en la moneda base
    elegida y la ``secondary`` en la otra moneda (VES/USD). Sus nombres siguen el
    patrón ``"<nombre>-<MONEDA>"`` (ej. ``Negocio-USD`` / ``Negocio-VES``). El
    capital inicial es EXTERNO (aportado en efectivo por el dueño, no sale de
    billeteras personales): se acredita a la cuenta principal al nacer.

    Args:
        user: dueño del negocio.
        name: nombre visible (único por usuario).
        currency: moneda base del negocio (``"VES"`` o ``"USD"``).
        initial_capital: capital inicial (>= 0) en la moneda base.

    Returns:
        El ``Business`` creado con sus dos cuentas.

    Raises:
        BusinessRuleError: si ya existe un negocio, el nombre está vacío, la
            moneda no es VES/USD o el capital inicial es negativo.
    """
    if Business.objects.filter(user=user).exists():
        raise BusinessRuleError("Ya tienes un negocio creado.")

    name = (name or "").strip()
    if not name:
        raise BusinessRuleError("El nombre del negocio no puede estar vacío.")

    currency = (currency or "").upper()
    if currency not in BUSINESS_CURRENCY_CODES:
        raise BusinessRuleError("La moneda del negocio debe ser VES o USD.")

    initial_capital = round_money(initial_capital)
    if initial_capital < 0:
        raise BusinessRuleError("El capital inicial no puede ser negativo.")

    business = Business.objects.create(user=user, name=name, currency=currency)

    primary = Wallet.objects.create(
        user=user,
        business=business,
        name=f"{name}-{currency}",
        currency=currency,
        tipo="business",
        color="#0891b2",
        role="primary",
    )
    secondary_currency = counterpart_currency(currency)
    Wallet.objects.create(
        user=user,
        business=business,
        name=f"{name}-{secondary_currency}",
        currency=secondary_currency,
        tipo="business",
        color="#7c3aed",
        role="secondary",
    )
    if initial_capital > 0:
        adjust_balance(primary, initial_capital, reason="capital_inicial")
    return business


def _to_base(amount: Decimal, currency: str, base: str, rate: Decimal) -> Decimal:
    """Convierte un monto a la moneda base del negocio (VES/USD).

    Args:
        amount: monto a convertir.
        currency: moneda de origen.
        base: moneda base del negocio.
        rate: Bs por 1 USD.

    Returns:
        El monto redondeado en la moneda base.
    """
    if currency == base:
        return round_money(amount)
    if base == "USD":
        return convert_to_usd(amount, currency, rate)
    return usd_to_currency(amount, base, rate)


def build_business_summary(business: Business, today: "date | None" = None) -> dict:
    """Agrega las métricas del dashboard del negocio.

    Todas las operaciones se acotan a LAS CUENTAS del negocio (principal y
    secundaria): lo personal jamás contamina estos totales. El saldo total se
    expresa en la moneda base, sumando la cuenta principal y la secundaria
    convertida con la tasa oficial.

    Args:
        business: negocio (con sus ``wallets`` cargadas).
        today: fecha de corte (por defecto, la local actual).

    Returns:
        Dict con ``saldo`` (total en moneda base), ``currency``, ``accounts``
        (detalle por cuenta), ``ingresos_mes``, ``egresos_mes`` y ``recent``
        (operaciones pagadas recientes, para el listado).
    """
    today = today or timezone.localdate()
    wallets = list(business.wallets.all())
    base = business.currency
    rate = get_current_official_rate()
    rate_value: "Decimal | None" = rate.effective_rate if rate else None
    one = rate_value or Decimal("1")

    month_start = today.replace(day=1)
    month_end = date(today.year + (today.month // 12), today.month % 12 + 1, 1)
    totals = (
        Transaction.objects.filter(
            wallet__business=business,
            estado="pagado",
            fecha_pagado__date__gte=month_start,
            fecha_pagado__date__lt=month_end,
        ).aggregate(
            ingresos=Sum("monto_usd", filter=Q(tipo="cobro")),
            egresos=Sum("monto_usd", filter=Q(tipo="pago")),
        )
    )

    recent = list(
        Transaction.objects.filter(wallet__business=business, estado="pagado")
        .select_related("category", "contact")
        .order_by("-fecha_pagado", "-fecha")[:6]
    )

    accounts = [
        {
            "id": str(w.pk),
            "name": w.name,
            "currency": w.currency,
            "role": w.role,
            "balance": str(round_money(w.saldo)),
        }
        for w in wallets
    ]
    total = sum(
        (_to_base(w.saldo, w.currency, base, one) for w in wallets), Decimal("0.00")
    )

    return {
        "saldo": str(round_money(total)),
        "currency": base,
        "accounts": accounts,
        "ingresos_mes": str(
            round_money(usd_to_currency(totals["ingresos"] or Decimal("0.00"), base, one))
        ),
        "egresos_mes": str(
            round_money(usd_to_currency(totals["egresos"] or Decimal("0.00"), base, one))
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


def _to_usd(amount: Decimal, currency: str, rate_value: Decimal) -> Decimal:
    """Convierte un monto de la moneda indicada a USD con la tasa oficial vigente.

    Un monto ya en USD se devuelve tal cual (identidad); cualquier otra moneda
    (ej. VES) se divide por la tasa (``rate_value``) para normalizar el tablero
    completo a dólares. Si no hay tasa disponible se usa la nominal para no
    romper el tablero (situación transitoria sin tasa oficial sembrada).
    """
    if currency == "USD":
        return amount
    return convert_to_usd(amount, currency, rate_value or Decimal("1"))


def _month_key(value: "date | datetime") -> date:
    """Normaliza el primer día del mes que devuelve ``TruncMonth`` a ``date``."""
    return value.date() if isinstance(value, datetime) else value


def build_business_analytics(
    business: Business,
    months: int = 12,
    today: "date | None" = None,
    month: "str | None" = None,
) -> dict:
    """Agrega las analíticas del negocio para el tablero financiero.

    Todo se acota a las billeteras del negocio (operaciones pagadas) y a sus
    facturas/pedidos/productos (el CRM). El tablero SIEMPRE se normaliza a USD
    (moneda de referencia de los reportes): las series con ``monto_usd`` ya están
    en dólares y los saldos/promedios en otra moneda (ej. VES) se dividen por la
    tasa oficial vigente. Así todos los KPIs, series y rankings comparten unidad.

    Args:
        business: negocio (con sus ``wallets`` cargadas).
        months: ventana de la serie P&L (3-24; el llamador ya lo clampea).
        today: fecha de corte (por defecto, la local actual).
        month: mes a inspeccionar en formato ``YYYY-MM``. Si se pasa, todo lo
            que es de periodo (KPIs de ingreso/egreso/margen, categorías y top
            clientes/proveedores) se acota a ese mes y la serie ``daily``
            devuelve el desglose por día. Un valor inválido se ignora (mes
            ``None``) en lugar de fallar, igual que hace ``months``.

    Returns:
        Dict con ``currency``, ``months``, ``month``, ``pnl``, ``daily``,
        ``incomeCategories``, ``expenseCategories``, ``aging``, ``topClients``,
        ``topSuppliers`` y ``kpis``. Los valores monetarios son números (float)
        redondeados y listos para graficar; las fechas usan formato ``YYYY-MM``
        (serie mensual) o ``YYYY-MM-DD`` (serie diaria, vacía sin mes elegido).
        Las magnitudes de estado (aging, por cobrar/por pagar, vencido e
        inventario) siempre describen el presente, nunca el mes elegido.
    """
    today = today or timezone.localdate()
    rate = get_current_official_rate()
    rate_value: "Decimal | None" = rate.effective_rate if rate else None
    one = rate_value or Decimal("1")

    selected: date | None = None
    if month:
        try:
            year_str, month_str = str(month).split("-")
            selected = date(int(year_str), int(month_str), 1)
        except (ValueError, TypeError):
            selected = None
    period_start = selected
    period_end = (
        date(
            selected.year + (selected.month // 12),
            selected.month % 12 + 1,
            1,
        )
        - timedelta(days=1)
        if selected is not None
        else None
    )

    cutoff = _first_day_months_back(today, months - 1)
    series = _month_series(today, months)

    def _date_window(field: str) -> dict:
        """Filtro de fechas del periodo: el mes elegido o la ventana completa."""
        if period_start is not None and period_end is not None:
            return {f"{field}__date__range": (period_start, period_end)}
        return {f"{field}__date__gte": cutoff}

    paid = Transaction.objects.filter(
        wallet__business=business, estado="pagado", tipo__in=["cobro", "pago"],
    )
    rows = (
        paid.filter(fecha_pagado__date__gte=cutoff)
        .annotate(month=TruncMonth("fecha_pagado"))
        .values("month", "tipo")
        .annotate(total=Sum("monto_usd"))
    )
    by_month = {(_month_key(row["month"]), row["tipo"]): row["total"] or Decimal("0.00") for row in rows}

    pnl = []
    income_total = Decimal("0.00")
    expense_total = Decimal("0.00")
    daily: list[dict] = []
    for m in series:
        income = _to_usd(by_month.get((m, "cobro"), Decimal("0.00")), "USD", one)
        expense = _to_usd(by_month.get((m, "pago"), Decimal("0.00")), "USD", one)
        # Sin mes elegido los KPIs de periodo suman la ventana entera; con mes
        # elegido se suman más abajo, solo de los días de ese mes.
        if selected is None:
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

    if period_start is not None and period_end is not None:
        # Desglose por día del mes elegido: se puebla la lista completa de días
        # del mes (los días sin operaciones van en cero) para que el gráfico
        # conserve el eje temporal aunque no haya movimientos.
        day_rows = (
            paid.filter(fecha_pagado__date__range=(period_start, period_end))
            .annotate(day=TruncDate("fecha_pagado"))
            .values("day", "tipo")
            .annotate(total=Sum("monto_usd"))
        )
        by_day = {(_month_key(row["day"]), row["tipo"]): row["total"] or Decimal("0.00") for row in day_rows}
        cursor = period_start
        while cursor <= period_end:
            income = _to_usd(by_day.get((cursor, "cobro"), Decimal("0.00")), "USD", one)
            expense = _to_usd(by_day.get((cursor, "pago"), Decimal("0.00")), "USD", one)
            income_total += income
            expense_total += expense
            daily.append(
                {
                    "date": cursor.strftime("%Y-%m-%d"),
                    "income": round(float(income), 2),
                    "expense": round(float(expense), 2),
                    "net": round(float(income - expense), 2),
                }
            )
            cursor += timedelta(days=1)

    def _categories(kind: str) -> list[dict]:
        grouped = (
            Transaction.objects.filter(
                wallet__business=business, estado="pagado", tipo=kind,
                **_date_window("fecha_pagado"),
            )
            .values("category__name")
            .annotate(total=Sum("monto_usd"))
            .order_by("-total")
        )
        return [
            {
                "label": row["category__name"] or "Sin categoría",
                "value": round(float(row["total"] or Decimal("0.00")), 2),
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
        value = _to_usd(inv.balance_due, inv.currency, one)
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
        payable += _to_usd(order.balance_due, order.currency, one)

    inventory_value = _to_usd(
        Product.objects.filter(business=business, kind="producto")
        .annotate(
            line_value=F("stock_quantity") * Coalesce(F("cost_price"), Decimal("0.00"))
        )
        .aggregate(total=Sum("line_value"))["total"]
        or Decimal("0.00"),
        business.currency,
        one,
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
            total = _to_usd(
                row["total"] or Decimal("0.00"), row["_currency"] or "USD", one
            )
            name = row["_name"] or "—"
            merged[name] = merged.get(name, Decimal("0.00")) + total
        top = sorted(merged.items(), key=lambda item: item[1], reverse=True)[:5]
        return [{"label": name, "value": round(float(total), 2)} for name, total in top]

    top_clients = _top_sources(
        InvoicePayment.objects.filter(
            invoice__business=business, **_date_window("paid_at")
        ),
        "invoice__contact__name",
        "invoice__currency",
    )
    top_suppliers = _top_sources(
        OrderPayment.objects.filter(
            order__business=business, **_date_window("paid_at")
        ),
        "order__contact__name",
        "order__currency",
    )

    margin_pct = round(float((income_total - expense_total) / income_total * 100), 1) if income_total > 0 else None

    return {
        "currency": "USD",
        "months": months,
        "month": selected.strftime("%Y-%m") if selected is not None else None,
        "pnl": pnl,
        "daily": daily,
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