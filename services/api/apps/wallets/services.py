"""services — Lógica de negocio de billeteras.

``adjust_balance`` es la ÚNICA puerta de entrada para modificar el saldo de una
billetera. Debe llamarse siempre dentro de una transacción de BD de Django
(``transaction.atomic``) para garantizar consistencia con las operaciones que
la provocan (marcar pagado, revertir, ajustar).

Integridad concurrente (auditoría C1): la fila se re-lee con
``select_for_update`` dentro de ``transaction.atomic`` ANTES de calcular el
nuevo saldo. Así dos operaciones simultáneas sobre la misma billetera se
serializan a nivel de fila (PostgreSQL) y la segunda valida contra el saldo ya
actualizado por la primera: no hay doble gasto ni pérdida de actualización.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction

from apps.core.currency import round_money
from apps.wallets.models import BalanceAuditLog, Wallet


@transaction.atomic
def adjust_balance(wallet: Wallet, delta: Decimal, *, reason: str = "") -> Decimal:
    """Aplica un delta (positivo o negativo) al saldo de una billetera.

    - El delta se redondea a 2 decimales antes de aplicar.
    - La fila se re-lee con ``select_for_update`` dentro de la transacción
      (C1): el cálculo y la validación usan SIEMPRE el saldo vigente en BD,
      no el objeto en memoria del caller.
    - Si el saldo resultante fuera negativo se rechaza (los cobros/pagos no
      pueden dejar una billetera en números rojos en el MVP).
    - Se escribe un ``BalanceAuditLog`` (C4) en la misma transacción: cada
      ajuste queda auditado con su delta, saldo resultante, motivo y usuario.
    - La instancia ``wallet`` del caller se actualiza en memoria al saldo
      nuevo para que los flujos que la reutilizan (mensajes, serializers,
      ``Transaction.objects.create``) queden consistentes.

    Args:
        wallet: billetera a modificar.
        delta: variación del saldo (Decimal). Cobro => positivo, pago => negativo.
        reason: texto descriptivo para logs/auditoría.

    Returns:
        El nuevo saldo de la billetera.

    Raises:
        ValueError: si el delta dejaría el saldo negativo.
    """
    delta = round_money(delta)
    locked = Wallet.objects.select_for_update().get(pk=wallet.pk)
    new_balance = round_money(locked.saldo + delta)
    if new_balance < 0:
        raise ValueError(
            f"Saldo insuficiente en '{locked.name}' "
            f"(disponible {locked.saldo:.2f})."
        )
    locked.saldo = new_balance
    locked.save(update_fields=["saldo", "updated_at"])
    # C4 — Auditoría de saldos: un registro por ajuste, DENTRO de la misma
    # transacción (si el log fallara, el ajuste se revierte completo).
    BalanceAuditLog.objects.create(
        wallet=locked,
        delta=delta,
        balance_after=new_balance,
        reason=reason or "",
        user_id=locked.user_id,
    )
    wallet.saldo = new_balance
    return new_balance