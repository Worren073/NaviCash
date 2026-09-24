"""services — Cierre de una lista de compras con registro del gasto.

Al completar la lista se elige la cuenta de pago y el total real; se genera una
operación de egreso ("pago") marcada como pagada sobre esa cuenta —descuenta el
saldo— y la lista queda cerrada. Todo ocurre en una sola transacción atómica
(patrón ``renew_subscription``), con la fila de la lista bloqueada para impedir
un doble completado.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.checklists.models import ShoppingList
from apps.core.currency import is_valid_amount, round_money
from apps.core.exceptions import BusinessRuleError
from apps.transactions.models import Transaction
from apps.transactions.services import compute_usd_equivalent, mark_paid
from apps.wallets.models import Wallet


@transaction.atomic
def complete_shopping_list(
    shopping_list: ShoppingList, wallet: Wallet, total_real: Decimal
) -> ShoppingList:
    """Completa la lista creando el egreso y descontando la cuenta elegida.

    Args:
        shopping_list: lista por completar (debe estar ``en_curso``).
        wallet: cuenta desde la que se pagó (propia y de la misma moneda).
        total_real: total efectivamente pagado (>= 0.01).

    Returns:
        La misma lista con estado ``completada``, cuenta y operación asignadas.

    Raises:
        BusinessRuleError: si la lista ya está completada, la cuenta no es
            propia o no coincide en moneda, o el saldo no alcanza.
    """
    # Bloqueo de fila: ante dos requests simultáneos solo uno completa (el otro
    # ve la lista ya completada y recibe 400).
    locked = ShoppingList.objects.select_for_update().get(pk=shopping_list.pk)

    if locked.estado == "completada":
        raise BusinessRuleError("La lista ya está completada.")
    if wallet.user_id != locked.user_id:
        raise BusinessRuleError("La cuenta debe pertenecerte.")
    if wallet.currency != locked.currency:
        raise BusinessRuleError("La cuenta debe usar la misma moneda de la lista.")
    if not is_valid_amount(total_real):
        raise BusinessRuleError("El total pagado debe ser mayor a 0.01.")

    # Verificación de integridad: todo listo, no se descuenta una lista con
    # productos sin precio/cantidad válidos (redundante con el frontend).
    has_invalid_items = locked.items.filter(
        Q(is_checked=False)
        | Q(precio_unitario__isnull=True)
        | Q(precio_unitario__lte=0)
        | Q(cantidad__lt=1)
    ).exists()
    if locked.items.count() == 0 or has_invalid_items:
        raise BusinessRuleError(
            "Todos los productos deben estar marcados con precio y cantidad válidos."
        )

    today = timezone.localdate()
    amount = round_money(total_real)

    usd = compute_usd_equivalent(amount, wallet.currency)
    tx = Transaction(
        user=locked.user,
        tipo="pago",
        monto=amount,
        moneda=wallet.currency,
        concepto=f"Compra: {locked.name}",
        wallet=wallet,
        fecha=today,
        monto_usd=usd["monto_usd"],
        tasa_usd=usd["tasa_usd"],
        fuente_tasa=usd["fuente_tasa"],
    )
    tx.save()
    # Descuenta la cuenta (egreso); lanza BusinessRuleError si el saldo no alcanza
    # y revierte TODA la transacción (no queda la operación huérfana).
    mark_paid(tx)

    locked.wallet = wallet
    locked.transaction = tx
    locked.total_real = amount
    locked.completed_at = timezone.now()
    locked.estado = "completada"
    locked.save(
        update_fields=["wallet", "transaction", "total_real", "completed_at", "estado", "updated_at"]
    )

    return locked