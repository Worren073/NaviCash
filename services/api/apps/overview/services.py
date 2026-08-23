"""services — Agregado de datos para el resumen del dashboard.

Responsabilidad: recoger wallets, operaciones y tasa del día en una sola
estructura plana *lista para serializar*. Todas las conversiones usan
``core.currency`` (decimales, nunca float).

Nota de conversión: la tasa oficial es VES por 1 USD. Las billeteras y los
totales se convierten con la tasa del día (valor actual), mientras que cada
operación conserva su equivalencia USD *congelada* al momento de registrarse.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db.models import Q, Sum
from django.utils import timezone

from apps.core.currency import convert_to_usd, round_money, usd_to_currency
from apps.rates.service import get_current_euro_rate, get_current_official_rate
from apps.transactions.models import Transaction
from apps.wallets.models import Wallet


def build_summary(user, today: date | None = None) -> dict:
    """Construye el resumen de home para un usuario.

    Valores devueltos:
    - ``base_currency``: moneda base del usuario.
    - ``rate``: tasa oficial del día (VES por 1 USD) o ``None`` si no hay.
    - ``total_balance_usd``: suma de saldos de billeteras en USD.
    - ``to_receive`` / ``to_pay``: totales pendientes vencidos en moneda base.
    - ``overdue``: total de operaciones retrasadas (por recibir + por pagar).
    - ``wallets``: billeteras con saldo local y ``usd_value`` virtual.
    - ``upcoming``: próximas 5 operaciones pendientes por vencimiento.

    Args:
        user: usuario autenticado (tiene ``wallets`` y ``transactions``).
        today: fecha de corte (por defecto, la local actual).

    Returns:
        Diccionario con los agregados listos para serializar.
    """
    today = today or timezone.localdate()
    base = user.base_currency
    rate = get_current_official_rate()
    rate_value: "Decimal | None" = rate.effective_rate if rate else None
    euro_rate = get_current_euro_rate()
    euro_rate_value: "Decimal | None" = euro_rate.effective_rate if euro_rate else None

    # --- Billeteras --------------------------------------------------------
    # Solo convertimos a USD las monedas para las que tenemos tasa (USD/VES);
    # EUR queda reportado en su moneda sin valor USD.
    wallets = list(Wallet.objects.filter(user=user).all())
    total_balance_usd = Decimal("0.00")
    total_balance_ves: "Decimal | None" = Decimal("0.00") if rate_value else None
    for w in wallets:
        usd_value = _to_usd_known(w.saldo, w.currency, rate_value)
        if usd_value is not None:
            total_balance_usd += usd_value
        w.usd_value = usd_value  # atributo virtual para el serializer
        # Agregado en moneda local bolívar (tasa del día) si es convertible.
        if total_balance_ves is not None:
            if w.currency == "VES":
                total_balance_ves += w.saldo
            elif w.currency == "USD":
                total_balance_ves += round_money(w.saldo * rate_value)

    # --- Operaciones pendientes --------------------------------------------
    pending = Transaction.objects.filter(user=user, estado="pendiente").select_related(
        "wallet", "category", "contact"
    )

    # Totales de TODAS las operaciones pendientes (no solo retrasadas):
    # En UNA sola agregación SQL (AUDIT M6) se calculan los totales por cobrar/pagar
    # y sus respectivos conteos.
    pending_totals = pending.aggregate(
        to_receive=Sum("monto_usd", filter=Q(tipo="cobro")),
        to_pay=Sum("monto_usd", filter=Q(tipo="pago")),
        count_to_receive=Sum(1, filter=Q(tipo="cobro")),
        count_to_pay=Sum(1, filter=Q(tipo="pago")),
    )
    to_receive_usd = pending_totals["to_receive"] or Decimal("0.00")
    to_pay_usd = pending_totals["to_pay"] or Decimal("0.00")
    count_to_receive = pending_totals["count_to_receive"] or 0
    count_to_pay = pending_totals["count_to_pay"] or 0

    to_receive = usd_to_currency(to_receive_usd, base, rate_value or Decimal("1"))
    to_pay = usd_to_currency(to_pay_usd, base, rate_value or Decimal("1"))

    # --- Totales retrasados para el indicador de alerta --------------------
    overdue_totals = pending.filter(fecha_vencimiento__lte=today).aggregate(
        overdue_total=Sum("monto_usd", filter=Q(tipo__in=["cobro", "pago"]))
    )
    overdue_usd = overdue_totals["overdue_total"] or Decimal("0.00")
    overdue = usd_to_currency(overdue_usd, base, rate_value or Decimal("1"))

    # --- Próximas operaciones ------------------------------------------------
    upcoming = list(
        pending.filter(fecha_vencimiento__gt=today).order_by("fecha_vencimiento")[:5]
    )

    # --- Actividad reciente --------------------------------------------------
    # Últimos cobros/pagos realmente ejecutados, para la sección del dashboard.
    recent = list(
        Transaction.objects.filter(user=user, estado="pagado")
        .select_related("wallet", "dest_wallet", "contact")
        .order_by("-fecha_pagado", "-fecha")[:6]
    )

    return {
        "base_currency": base,
        "rate": rate_value,
        "euro_rate": euro_rate_value,
        "total_balance_usd": round_money(total_balance_usd),
        "total_balance_ves": round_money(total_balance_ves) if total_balance_ves is not None else None,
        "to_receive": to_receive,
        "to_pay": to_pay,
        "count_to_receive": count_to_receive,
        "count_to_pay": count_to_pay,
        "overdue": round_money(overdue),
        "wallets": wallets,
        "upcoming": upcoming,
        "recent": recent,
    }


def _to_usd_known(amount: Decimal, currency: str, rate_value: "Decimal | None") -> "Decimal | None":
    """Convierte a USD solo si existe tasa para la moneda; si no, ``None``.

    Args:
        amount: cantidad en la moneda original.
        currency: código ISO de la moneda (USD, VES, EUR...).
        rate_value: unidades de VES por 1 USD (o ``None`` si no hay tasa).

    Returns:
        Equivalente USD redondeado, o ``None`` si no hay tasa aplicable.
    """
    if currency == "USD":
        return round_money(amount)
    if currency == "VES" and rate_value and rate_value > 0:
        return convert_to_usd(amount, currency, rate_value)
    return None


def aggregate_by_category(user, kind: str) -> list[dict]:
    """Operaciones de un tipo agrupadas por categoría (para gráficos).

    La suma se hace íntegra en SQL (``values().annotate()``) y solo la
    conversión a la moneda base queda en Python (AUDIT M6): antes se cargaban
    TODAS las operaciones y se agregaba fila a fila.

    Args:
        user: usuario autenticado.
        kind: tipo de operación ("cobro" o "pago").

    Returns:
        Lista de ``{"category": nombre, "total": monto en moneda base}``
        ordenada de mayor a menor.
    """
    rate = get_current_official_rate()
    rate_value: "Decimal | None" = rate.effective_rate if rate else None

    rows = (
        Transaction.objects.filter(user=user, tipo=kind)
        .values("category__name")
        .annotate(total=Sum("monto_usd"))
        .order_by("-total")
    )
    return [
        {
            "category": name or "Sin categoría",
            "total": round_money(
                usd_to_currency(total, user.base_currency, rate_value or Decimal("1"))
            ),
        }
        for name, total in rows.values_list("category__name", "total")
    ]