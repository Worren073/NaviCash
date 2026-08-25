"""services — Reglas de negocio de operaciones (transiciones, conversión, saldos).

Todas las funciones mutan estado en una transacción de BD atómica (R9):

+------------------+---------------------------------------------------------+
| Transición        | Efecto sobre la billetera                                |
+------------------+---------------------------------------------------------+
| pendiente→pagado  | Cobro suma / Pago resta al saldo                        |
| pagado→cancelado  | Se revierte el efecto anterior                          |
| pagado→pendiente  | Se revierte el efecto anterior                          |
+------------------+---------------------------------------------------------+
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.core.currency import (  # noqa: F401
    REFERENCE_CURRENCY,
    convert_to_usd,
    is_valid_amount,
    round_money,
)
from apps.core.exceptions import BusinessRuleError
from apps.rates.service import (
    get_current_euro_rate,
    get_current_official_rate,
    get_usd_rate_for_conversion,
)
from apps.transactions.models import TRANSACTION_STATES, Transaction
from apps.wallets.models import Wallet
from apps.wallets.services import adjust_balance


def compute_usd_equivalent(monto: Decimal, moneda: str) -> dict:
    """Calcula la conversión a USD congelada para una operación.

    Args:
        monto: cantidad en la moneda original.
        moneda: código ISO de la moneda original.

    Returns:
        Dict con ``monto_usd``, ``tasa_usd`` y ``fuente_tasa``.
    """
    if moneda == REFERENCE_CURRENCY:
        # Operación directa en USD: tasa = 1, sin consultar a la API.
        return {"monto_usd": monto, "tasa_usd": Decimal("1"), "fuente_tasa": "usd"}

    rate = get_usd_rate_for_conversion()
    monto_usd = convert_to_usd(monto, moneda, rate)
    return {"monto_usd": monto_usd, "tasa_usd": rate, "fuente_tasa": "oficial"}


def _apply_to_wallet(tx: Transaction, *, reverse: bool = False) -> None:
    """Aplica (o revierte) el efecto de una operación pagada sobre su billetera.

    Args:
        tx: operación (debe tener wallet y estado coherente).
        reverse: si True, deshace el efecto (para cancelar/revertir).

    Raises:
        BusinessRuleError: si no hay billetera o el saldo quedaría negativo.
    """
    if tx.wallet is None:
        return  # Sin billetera asignada no hay efecto de saldo.
    delta = tx.monto if tx.tipo == "cobro" else -tx.monto
    if reverse:
        delta = -delta
    try:
        adjust_balance(tx.wallet, delta, reason=f"transaction-{tx.pk}")
    except ValueError as exc:  # saldo insuficiente al revertir
        raise BusinessRuleError(str(exc)) from exc


@transaction.atomic
def mark_paid(tx: Transaction, paid_at: datetime | None = None) -> Transaction:
    """Marca la operación como pagada y actualiza la billetera (ADR-08).

    Args:
        tx: operación pendiente (o cancelada) a pagar.
        paid_at: instante del pago (por defecto ahora).

    Returns:
        La misma operación con estado ``pagado``.

    Raises:
        BusinessRuleError: si ya estaba pagada.
    """
    if tx.estado == "pagado":
        raise BusinessRuleError("Esta operación ya está pagada.")
    if tx.estado == "cancelado":
        # Se permite reactivar una cancelada: no había efecto de saldo previo.
        pass
    _apply_to_wallet(tx)
    tx.estado = "pagado"
    tx.fecha_pagado = paid_at or timezone.now()
    tx.save(update_fields=["estado", "fecha_pagado", "updated_at"])
    return tx


@transaction.atomic
def cancel(tx: Transaction) -> Transaction:
    """Cancela la operación; si estaba pagada revierte la billetera.

    Args:
        tx: operación a cancelar.

    Returns:
        La operación con estado ``cancelado``.
    """
    if tx.estado == "pagado":
        _apply_to_wallet(tx, reverse=True)
    tx.estado = "cancelado"
    tx.fecha_pagado = None
    tx.save(update_fields=["estado", "fecha_pagado", "updated_at"])
    return tx


@transaction.atomic
def revert_to_pending(tx: Transaction) -> Transaction:
    """Devuelve la operación a estado pendiente (revierte billetera si pagó).

    Args:
        tx: operación pagada o cancelada.

    Returns:
        La operación con estado ``pendiente``.
    """
    if tx.estado == "pagado":
        _apply_to_wallet(tx, reverse=True)
    tx.estado = "pendiente"
    tx.fecha_pagado = None
    tx.save(update_fields=["estado", "fecha_pagado", "updated_at"])
    return tx


@transaction.atomic
def set_state(tx: Transaction, new_state: str) -> Transaction:
    """Punto único de cambio de estado con las reglas de negocio.

    Args:
        tx: operación.
        new_state: uno de los estados de ``TRANSACTION_STATES``.

    Returns:
        La operación actualizada.

    Raises:
        BusinessRuleError: si la transición no es válida o ya está en ese estado.
    """
    valid = {s[0] for s in TRANSACTION_STATES}
    if new_state not in valid:
        raise BusinessRuleError(f"Estado inválido: {new_state}.")
    if new_state == tx.estado:
        raise BusinessRuleError(f"La operación ya está {tx.get_estado_display().lower()}.")

    if new_state == "pagado":
        return mark_paid(tx)
    if new_state == "cancelado":
        return cancel(tx)
    return revert_to_pending(tx)


def _resolve_transfer_rate(source_currency: str, dest_currency: str, rate_fuente: str, custom_rate: "Decimal | None") -> "Decimal | None":
    """Resuelve la tasa a usar en una transferencia entre monedas distintas.

    Args:
        source_currency: moneda de la billetera origen.
        dest_currency: moneda de la billetera destino.
        rate_fuente: ``"oficial"`` (BCV USD), ``"euro"`` (BCV EUR) o ``"manual"``.
        custom_rate: tasa personalizada (solo si ``rate_fuente == "manual"``).

    Returns:
        La tasa Decimal (> 0) a aplicar.

    Raises:
        BusinessRuleError: si la tasa no existe, no es positiva o la combinación
            de monedas no es convertible entre sí (solo USD<->VES en el MVP).
    """
    if source_currency == dest_currency:
        return None  # misma moneda: no hace falta tasa

    supported = {"USD", "VES"}
    if {source_currency, dest_currency} == supported:
        if rate_fuente == "oficial":
            rate = get_current_official_rate().effective_rate
        elif rate_fuente == "euro":
            # Alternativa de compra/venta de divisas: la tasa oficial del
            # euro (VES por 1 EUR) usada como referencia para el traspaso.
            rate = get_current_euro_rate().effective_rate
        else:
            if custom_rate is not None and custom_rate > 0:
                rate = custom_rate
            else:
                raise BusinessRuleError("Debes indicar una tasa personalizada mayor a cero.")
        if not rate or rate <= 0:
            raise BusinessRuleError("No hay una tasa disponible.")
        return rate

    raise BusinessRuleError(
        f"No se puede transferir entre {source_currency} y {dest_currency}: "
        "solo se soporta la conversión USD↔VES."
    )


@transaction.atomic
def create_transfer(
    source: Wallet,
    dest: Wallet,
    amount: Decimal,
    *,
    rate_fuente: str = "manual",
    custom_rate: "Decimal | None" = None,
    concepto: str = "",
) -> Transaction:
    """Transfiere dinero entre dos billeteras del mismo usuario.

    - Misma moneda: sólo mueve ``amount`` (tasa 1).
    - Monedas distintas: aplica la tasa (BCV o personalizada).
      - USD -> VES (venta): ``destino = amount * tasa``.
      - VES -> USD (compra): ``destino = amount / tasa``.
    - Registra una operación ``tipo="transferencia"`` ya pagada con ambos
      monederos y deja el saldo ajustado de forma atómica.

    Args:
        source: billetera de origen.
        dest: billetera de destino.
        amount: cantidad a transferir (moneda de ``source``).
        rate_fuente: ``"oficial"`` (BCV USD), ``"euro"`` (BCV EUR) o ``"manual"``.
        custom_rate: tasa manual si ``rate_fuente == "manual"``.
        concepto: texto opcional del concepto.

    Returns:
        La operación de transferencia creada (con estado ``pagado``).

    Raises:
        BusinessRuleError: si las reglas de negocio no se cumplen
            (mismo monedero, user distinto, saldo insuficiente, tasa inválida).
    """
    if source.id == dest.id:
        raise BusinessRuleError("No puedes transferir a la misma cuenta.")
    if source.user_id != dest.user_id:
        raise BusinessRuleError("Las cuentas deben pertenecerte.")
    if not is_valid_amount(amount):
        raise BusinessRuleError("El monto a transferir debe ser mayor a 0.01.")

    rate = _resolve_transfer_rate(source.currency, dest.currency, rate_fuente, custom_rate)

    if rate is None:
        dest_amount = round_money(amount)
    elif source.currency == "USD":  # venta: entrego dólares
        dest_amount = round_money(amount * rate)
    else:  # compra: entrego bolívares
        dest_amount = round_money(amount / rate)

    try:
        adjust_balance(source, -amount, reason="transfer-out")
        adjust_balance(dest, dest_amount, reason="transfer-in")
    except ValueError as exc:
        raise BusinessRuleError(str(exc)) from exc

    usd_conversion = compute_usd_equivalent(amount, source.currency)
    concepto = concepto or f"Transferencia: {source.name} → {dest.name}"

    return Transaction.objects.create(
        user_id=source.user_id,
        tipo="transferencia",
        estado="pagado",
        monto=amount,
        moneda=source.currency,
        wallet=source,
        dest_wallet=dest,
        monto_destino=dest_amount,
        moneda_destino=dest.currency,
        tasa_uso=rate or Decimal("1"),
        tasa_fuente=rate_fuente,
        concepto=concepto,
        fecha_pagado=timezone.now(),
        **usd_conversion,
    )


@transaction.atomic
def register_transaction(
    user,
    *,
    tipo: str,
    monto: Decimal,
    moneda: str,
    concepto: str = "",
    wallet: "Wallet | None" = None,
    estado: str = "pagado",
    fecha: "datetime.date | None" = None,
) -> Transaction:
    """Registra un cobro (ingreso) o pago (egreso) y ajusta la billetera.

    Es el punto único de alta de operaciones tipo "registro" sin contacto ni
    transferencia (usado por el asistente Navi y útil para el API en general).

    Args:
        user: usuario dueño de la operación.
        tipo: ``"cobro"`` (suma al saldo) o ``"pago"`` (resta al saldo).
        monto: cantidad en la moneda original.
        moneda: código ISO de la moneda original.
        concepto: texto corto del concepto.
        wallet: billetera propia y de la misma moneda (opcional).
        estado: ``"pagado"`` aplica el efecto de saldo de inmediato.

    Returns:
        La operación creada (y pagada si ``estado == "pagado"``).

    Raises:
        BusinessRuleError: si el tipo no es cobro/pago, el monto es inválido
            o la billetera no es propia o no coincide en moneda.
    """
    if tipo not in {"cobro", "pago"}:
        raise BusinessRuleError("Tipo no soportado: solo cobro o pago.")
    if not is_valid_amount(monto):
        raise BusinessRuleError("El monto debe ser mayor a 0.01.")
    if wallet is not None:
        if wallet.user_id != user.id:
            raise BusinessRuleError("La billetera debe pertenecerte.")
        if wallet.currency != moneda:
            raise BusinessRuleError("La billetera debe usar la misma moneda que la operación.")

    usd_conversion = compute_usd_equivalent(monto, moneda)
    tx = Transaction.objects.create(
        user=user,
        tipo=tipo,
        estado="pendiente",
        monto=monto,
        moneda=moneda,
        concepto=concepto,
        wallet=wallet,
        fecha=fecha or timezone.localdate(),
        **usd_conversion,
    )
    if estado == "pagado":
        mark_paid(tx)
    try:
        from apps.assistant.memory import learn_from_transaction
        learn_from_transaction(user, tx)
    except Exception:  # noqa: BLE001
        pass
    return tx