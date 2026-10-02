"""services — Lógica de negocio del módulo Business.

``create_business`` es la ÚNICA puerta de entrada para crear un negocio: crea
su billetera (tipo ``business``) y acredita el capital inicial vía
``adjust_balance`` (auditoría ``capital_inicial``, ADR-08). El resumen del
dashboard agrega SIEMPRE solo la billetera del negocio: nunca ve lo personal.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from apps.business.models import Business
from apps.core.currency import round_money, usd_to_currency
from apps.core.exceptions import BusinessRuleError
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