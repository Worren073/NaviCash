"""services — Lógica de negocio de ahorro.

``add_contribution`` centraliza la conversión a la moneda de la meta (con tasa
congelada) y evita operar directamente sobre el queryset de aportes.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction

from apps.core.currency import REFERENCE_CURRENCY, convert_to_usd
from apps.core.exceptions import BusinessRuleError
from apps.rates.service import get_usd_rate_for_conversion
from apps.savings.models import GoalContribution, SavingsGoal


@transaction.atomic
def add_contribution(
    goal: SavingsGoal,
    *,
    amount: Decimal,
    currency: str,
    user,
    wallet=None,
    note: str = "",
) -> GoalContribution:
    """Añade un aporte a una meta convirtiéndolo a la moneda de la meta.

    La conversión usa la tasa oficial del día y se congela en
    ``amount_goal_currency`` (R2/R4).

    Args:
        goal: meta a la que aportar.
        amount: cantidad aportada.
        currency: moneda original del aporte.
        user: usuario autenticado (dueño de la meta).
        wallet: billetera de origen opcional (debe ser del usuario).
        note: nota opcional.

    Returns:
        El ``GoalContribution`` creado.

    Raises:
        BusinessRuleError: si la meta no pertenece al usuario, la billetera es
            ajena, o la conversión falla.
    """
    if goal.user_id != user.id:
        raise BusinessRuleError("La meta no pertenece al usuario.")

    if wallet is not None and wallet.user_id != user.id:
        raise BusinessRuleError("La billetera de origen no pertenece al usuario.")

    if goal.currency == currency:
        # Misma moneda: aporte directo, sin conversión.
        amount_in_goal = amount
    elif goal.currency == REFERENCE_CURRENCY:
        # La meta está en USD: convertimos con la tasa oficial del día.
        rate_usd = get_usd_rate_for_conversion()
        amount_in_goal = convert_to_usd(amount, currency, rate_usd)
    else:
        # Conversión entre dos monedas no-USD: no soportada en el MVP.
        raise BusinessRuleError(
            "Por ahora las metas solo aceptan aportes en su misma moneda o en USD."
        )

    return GoalContribution.objects.create(
        user=user,
        goal=goal,
        amount=amount,
        currency=currency,
        amount_goal_currency=amount_in_goal,
        wallet=wallet,
        note=note,
    )