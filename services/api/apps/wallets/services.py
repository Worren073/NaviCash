"""services — Lógica de negocio de billeteras.

``adjust_balance`` es la ÚNICA puerta de entrada para modificar el saldo de una
billetera. Debe llamarse siempre dentro de una transacción de BD de Django
(``transaction.atomic``) para garantizar consistencia con las operaciones que
la provocan (marcar pagado, revertir, ajustar).
"""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction

from apps.core.currency import round_money
from apps.wallets.models import Wallet


@transaction.atomic
def adjust_balance(wallet: Wallet, delta: Decimal, *, reason: str = "") -> Decimal:
    """Aplica un delta (positivo o negativo) al saldo de una billetera.

    - El delta se redondea a 2 decimales antes de aplicar.
    - Si el saldo resultante fuera negativo se rechaza (los cobros/pagos no
      pueden dejar una billetera en números rojos en el MVP).

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
    new_balance = round_money(wallet.saldo + delta)
    if new_balance < 0:
        raise ValueError(
            f"Saldo insuficiente en '{wallet.name}' "
            f"(disponible {wallet.saldo:.2f})."
        )
    wallet.saldo = new_balance
    wallet.save(update_fields=["saldo", "updated_at"])
    return new_balance