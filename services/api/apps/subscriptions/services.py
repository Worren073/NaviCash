"""services — Renovación de mensualidades con registro del gasto.

Al renovar se crea una operación de egreso ("pago") marcada como pagada sobre
la cuenta seleccionada —esto resta saldo— y la mensualidad se recicla para un
nuevo período: inicia hoy y dura lo mismo que el período anterior.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import BusinessRuleError
from apps.subscriptions.models import Subscription
from apps.transactions.models import Transaction
from apps.transactions.services import compute_usd_equivalent, mark_paid
from apps.wallets.models import Wallet


@transaction.atomic
def renew_subscription(subscription: Subscription, wallet: Wallet, amount: Decimal) -> Subscription:
    """Renueva la mensualidad creando el gasto sobre la cuenta elegida.

    Args:
        subscription: mensualidad a renovar (debe ser renovable).
        wallet: cuenta de donde se pagó el gasto.
        amount: monto del gasto en la moneda de la cuenta.

    Returns:
        La misma mensualidad con el período extendido.

    Raises:
        BusinessRuleError: si la mensualidad no es renovable o el monto es inválido.
    """
    if not subscription.can_renew:
        raise BusinessRuleError("La mensualidad no está en período de renovación.")

    today = timezone.localdate()

    usd = compute_usd_equivalent(amount, wallet.currency)
    tx = Transaction(
        user=subscription.user,
        tipo="pago",
        monto=amount,
        moneda=wallet.currency,
        concepto=f"Renovación: {subscription.name}",
        wallet=wallet,
        fecha=today,
        monto_usd=usd["monto_usd"],
        tasa_usd=usd["tasa_usd"],
        fuente_tasa=usd["fuente_tasa"],
    )
    tx.save()
    mark_paid(tx)  # ajusta el saldo de la cuenta (egreso).

    # El nuevo período dura lo mismo que el anterior (mínimo 1 día).
    previous_duration = max(1, subscription.days_total)
    subscription.start_date = today
    subscription.end_date = today + timedelta(days=previous_duration)
    subscription.save(update_fields=["start_date", "end_date", "updated_at"])

    return subscription