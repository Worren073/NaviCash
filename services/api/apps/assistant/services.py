"""services — Orquestación del asistente Navi.

Flujo de una petición:
1. Validar + persistir el mensaje del usuario (si hay historial activado).
2. Construir el contexto con ``build_context``.
3. Decidir el camino del turno (en este orden):
   a. Intento PELIGROSO (dinero ajeno, borrado, credenciales) → rechazo firme,
      sin tocar el LLM ni la base de datos.
   b. Confirmación de una acción pendiente (cache por sesión) → ejecuta
      (transferencia, cobro o pago).
   c. Registro de cobro/pago/transferencia detectado por ``extract_action``:
      - incompleto → Navi pregunta por los datos faltantes;
      - completo → pide confirmación explícita ("sí") antes de ejecutar.
   d. Inyección de prompt → rechazo determinista (o respuesta del LLM endurecido).
   e. Resto → proveedor configurado (openai) o fallback determinista.
4. Devolver el texto de respuesta y la sesión agrupadora.

La orquestación desconoce el transporte: recibe ``user`` + ``message`` y
devuelve un dict plano listo para serializar.
"""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal

from django.core.cache import cache

from apps.assistant.actions import (
    ActionProposal,
    answer_dangerous,
    extract_currency_code,
    is_confirmation,
    is_dangerous,
    is_decline,
)
from apps.assistant.context import build_context
from apps.assistant.intent_rules import answer_deterministic
from apps.assistant.providers import (
    MockAssistantProvider,
    TranscriptionProviderError,
    get_provider,
    get_transcriber,
)
from apps.core.exceptions import BusinessRuleError
from apps.rates.service import get_eur_rate_for_conversion, get_usd_rate_for_conversion

logger = logging.getLogger(__name__)

#: TTL de las transferencias pendientes de confirmar (10 minutos).
PENDING_TTL_SECONDS = 600

#: Mensajes accionables para los errores del proveedor de transcripción.
PROVIDER_ERROR_MESSAGES = {
    "auth": "La clave del servicio de transcripción no es válida.",
    "forbidden": (
        "El servicio de transcripción no está disponible en tu región "
        "o la clave no tiene permisos para audio."
    ),
    "quota": "Se alcanzó el límite del servicio de transcripción. Intenta de nuevo más tarde.",
    "format": "No pude procesar el audio (el formato no es compatible).",
    "provider": "El servicio de transcripción no está disponible. Intenta de nuevo.",
}


def chat(user, message: str, session_id: "uuid.UUID | None" = None) -> dict:
    """Procesa un turno: registro/seguridad por determinismo + respuesta.

    Args:
        user: usuario autenticado.
        message: texto del usuario (ya validado/normalizado).
        session_id: uuid de la sesión (se asigna uno nuevo si falta).

    Returns:
        Dict ``{"text": str, "session_id": str}`` con la respuesta de Navi.
    """
    session_id = session_id or uuid.uuid4()
    context = build_context(user)
    pending_key = _pending_key(user, session_id)
    pending = cache.get(pending_key)

    text: str | None = None

    # 1. Bloqueo total de intentos peligrosos.
    if is_dangerous(message):
        text = answer_dangerous()

    # 1.5. Rechazo de pendiente: si hay algo pendiente y el usuario dice "no",
    # cancelar la operación y limpiar el cache.
    elif pending and is_decline(message):
        cache.delete(pending_key)
        text = (
            "Entendido, no registro nada. "
            "Avísame si necesitas consultar tu balance o registrar algo después."
        )

    # 2. Confirmaciones pendientes (cache por sesión).
    elif is_confirmation(message) and pending:
        if pending.get("step") == "confirm":
            # Acción esperando el «sí» explícito → se ejecuta.
            # Idempotencia (AUDIT C2): con gunicorn multi-worker dos «sí»
            # concurrentes podrían ejecutar la acción dos veces.
            # cache.add es atómico (SET NX): solo el primer worker obtiene el
            # lock de 60 s y ejecuta; los demás responden sin tocar la BD.
            lock_key = f"{pending_key}:executing"
            if not cache.add(lock_key, 1, 60):
                text = "Estoy procesando tu confirmación, un momento"
            else:
                try:
                    text = _execute_pending(user, pending, session_id)
                finally:
                    cache.delete(pending_key)
                    cache.delete(lock_key)
        else:
            # Respuesta a una pregunta de datos faltantes: intenta completar
            # («sí, fue en Banesco»); si no aporta datos, se repite la pregunta.
            text = _complete_or_repeat(user, context, pending_key, pending, message)

    # 3. Intento de registro (cobro/pago/transferencia) y estado pendiente.
    # TEMPORAL: deshabilitado para testear acciones solo por LLM (function calling).
    # Cuando se reactive, descomentar el bloque y eliminar esta nota.
    #
    # else:
    #     proposal = extract_action(context, message)
    #     if proposal is not None and proposal.complete:
    #         text = _handle_complete(user, context, proposal, pending_key)
    #     elif pending and pending.get("step") == "fill":
    #         text = _complete_or_repeat(user, context, pending_key, pending, message)
    #     elif proposal is not None:
    #         cache.set(pending_key, _proposal_to_cache(proposal), PENDING_TTL_SECONDS)
    #         text = _ask_for(proposal, context)

    # 4/5. Respuesta normal: proveedor (LLM con tools o SYSTEM_PROMPT endurecido)
    # o fallback determinista. Las inyecciones de prompt caen aquí: si el LLM
    # está disponible responde endurecido; el fallback sin red las rechaza.
    if text is None:
        provider = get_provider()
        history = _load_history(user, session_id, limit=6)
        try:
            text = provider.answer(context, [*history, {"role": "user", "content": message}])
            # Si el provider es Gemini con tools y dejó una propuesta pendiente
            # (register/transfer via tool call), cachearla para la confirmación.
            if hasattr(provider, "last_pending") and provider.last_pending:
                cache.set(pending_key, provider.last_pending, PENDING_TTL_SECONDS)
        except Exception as exc:  # noqa: BLE001 — nunca dejar de responder
            logger.warning("Fallback determinista por error del proveedor: %s", exc)
            text = answer_deterministic(context, message)

    _persist_chat(user, session_id, message, text)
    return {"text": text, "session_id": str(session_id)}


# ---------------------------------------------------------------------------
# Registro de cobros / pagos (ejecución directa)
# ---------------------------------------------------------------------------


def _execute_ledger(user, proposal: ActionProposal) -> str:
    """Registra un cobro/pago claro y devuelve el resumen para el usuario.

    Si el monto se dijo en una moneda pero se confirma una cuenta en otra
    (ej.: 50 USD → cuenta VES), se convierte con la tasa oficial BCV y el
    registro queda en la moneda de la cuenta.
    """
    from apps.transactions.services import register_transaction, round_money
    from apps.wallets.models import Wallet

    wallet = None
    if proposal.wallet_name:
        wallet = Wallet.objects.filter(user=user, name=proposal.wallet_name).first()

    monto = proposal.monto
    conversion_txt = None
    if proposal.convertir and proposal.moneda_original and proposal.moneda_original != proposal.moneda:
        # Use custom rate if provided, otherwise fall back to official BCV.
        if proposal.tasa and proposal.tasa > 0:
            rate = proposal.tasa
            rate_source = proposal.tipo_tasa or "personalizada"
        elif proposal.tipo_tasa == "euro":
            rate = get_eur_rate_for_conversion()
            rate_source = "euro"
        else:
            rate = get_usd_rate_for_conversion()
            rate_source = "oficial"

        if rate <= Decimal("1"):
            return (
                f"No tengo disponible la tasa para convertir "
                f"{proposal.monto:,.2f} {proposal.moneda_original} a "
                f"{proposal.moneda}. Dime el monto ya convertido "
                f"(ej.: «{proposal.monto:,.2f} dólares» → el equivalente en bolívares)."
            )
        if proposal.moneda_original == "USD":
            monto_final = round_money(proposal.monto * rate)
        else:  # moneda original VES -> cuenta USD: se divide por la tasa
            monto_final = round_money(proposal.monto / rate)
        conversion_txt = (
            f"Conversión: {proposal.monto:,.2f} {proposal.moneda_original} → "
            f"{monto_final:,.2f} {proposal.moneda} (tasa {rate_source} {rate:,.2f})"
        )
        monto = monto_final

    try:
        tx = register_transaction(
            user,
            tipo=proposal.tipo,
            monto=monto,
            moneda=proposal.moneda,
            concepto=proposal.concepto,
            wallet=wallet,
            estado="pagado",
        )
    except BusinessRuleError:
        return (
            "El modo agéntico para registros no se encuentra disponible en estos "
            "momentos. Por favor ingrese la transacción de manera manual o "
            "intente más tarde."
        )

    return _ledger_confirm_text(tx, conversion=conversion_txt)


def _ledger_confirm_text(tx, conversion: "str | None" = None) -> str:
    """Resumen legible de un cobro/pago recién registrado.

    ``conversion``: texto opcional con el detalle de la conversión aplicada
    (p. ej. "Conversión: 50.00 USD → 3,096.76 VES (tasa oficial 61.94)").
    """
    label = "cobro" if tx.tipo == "cobro" else "pago"
    monto = f"{tx.monto:,.2f} {tx.moneda}"
    saldo = f"{tx.wallet.saldo:,.2f} {tx.moneda}" if tx.wallet else "—"
    wallet_txt = f" en «{tx.wallet.name}»" if tx.wallet else ""
    concept_txt = f" · Concepto: {tx.concepto}" if tx.concepto else ""
    conv_txt = f"\n{conversion}." if conversion else ""
    return (
        f"✅ Listo. Registré un **{label}** de {monto}{wallet_txt}."
        f"{concept_txt}{conv_txt}\nTu saldo en esa cuenta quedó en {saldo}."
    )


# ---------------------------------------------------------------------------
# Transferencias (requieren confirmación explícita)
# ---------------------------------------------------------------------------


def _execute_transfer(user, pending: dict, session_id: uuid.UUID) -> str:
    """Ejecuta la transferencia previamente confirmada por el usuario."""
    from apps.transactions.services import create_transfer
    from apps.wallets.models import Wallet

    source = Wallet.objects.filter(user=user, name=pending.get("wallet_name")).first()
    dest = Wallet.objects.filter(user=user, name=pending.get("dest_wallet_name")).first()

    if not source or not dest:
        return (
            "No puedo transferir: ya no encuentro alguna de las cuentas de la "
            "transferencia pendiente. Repítemela y la revisamos."
        )

    try:
        if pending.get("divisa") and pending.get("tasa"):
            tx = create_transfer(
                source,
                dest,
                Decimal(pending["monto"]),
                rate_fuente="manual",
                custom_rate=Decimal(pending["tasa"]),
                concepto=pending.get("concepto", ""),
            )
        else:
            tx = create_transfer(
                source,
                dest,
                Decimal(pending["monto"]),
                rate_fuente="oficial",
                concepto=pending.get("concepto", ""),
            )
    except BusinessRuleError:
        return (
            "El modo agéntico para registros no se encuentra disponible en estos "
            "momentos. Por favor ingrese la transferencia de manera manual o "
            "intente más tarde."
        )

    return _transfer_confirm_text(tx)


def _execute_pending(user, pending: dict, session_id: uuid.UUID) -> str:
    """Ejecuta la acción confirmada por el usuario (cobro, pago o transferencia)."""
    tipo = pending.get("tipo")
    if tipo == "transferencia":
        return _execute_transfer(user, pending, session_id)

    # Cobro o pago
    proposal = _cached_to_proposal(pending)
    return _execute_ledger(user, proposal)


def _transfer_confirm_text(tx) -> str:
    """Resumen legible de una transferencia ejecutada."""
    monto = f"{tx.monto:,.2f} {tx.moneda}"
    dest_txt = (
        f"{tx.monto_destino:,.2f} {tx.moneda_destino}" if tx.monto_destino else monto
    )
    return (
        f"✅ Listo. Transferí {monto} de «{tx.wallet.name}» a «{tx.dest_wallet.name}» "
        f"({dest_txt}). Tus saldos ya quedaron ajustados."
    )


# ---------------------------------------------------------------------------
# Preguntas de Navi (datos faltantes / confirmación)
# ---------------------------------------------------------------------------


def _ask_for(proposal: ActionProposal, context: dict) -> str:
    """Pide los datos que faltan para completar el registro (sin tocar la BD)."""
    verb = "recibiste" if proposal.tipo == "cobro" else "pagaste"

    msgs = []
    monto_falta = "monto" in proposal.missing and proposal.monto is None
    if monto_falta and proposal.tipo != "transferencia":
        # «Acabo de comprar un café» (sin monto): primero se ofrece registrar.
        label = "pago" if proposal.tipo == "pago" else "cobro"
        extra = (
            " y en qué cuenta"
            if "wallet" in proposal.missing
            else ""
        )
        msgs.append(
            f"¿Te gustaría que registre ese {label} por ti? Por cierto, dime cuánto fue"
            f"{extra} y lo anoto por ti (ej.: «15 dólares en efectivo»)."
        )
    elif "monto" in proposal.missing and proposal.tipo == "transferencia":
        msgs.append(
            f"¿De cuánto fue la transferencia de «{proposal.wallet_name}» a "
            f"«{proposal.dest_wallet_name}»? Dime el monto (ej.: «150 dólares») "
            "y lo confirmo contigo antes de ejecutarla."
        )
    elif "monto" in proposal.missing:
        msgs.append(f"¿De cuánto fue el {proposal.tipo}? Dime el monto y lo registro.")
    if "razon" in proposal.missing:
        monto_txt = (
            f" de {proposal.monto:,.2f} {proposal.moneda}" if proposal.monto is not None else ""
        )
        msgs.append(
            f"¿Cuál es el motivo del {proposal.tipo}{monto_txt}? "
            "Dímelo en una frase y lo guardo con ese concepto."
        )
    if "moneda" in proposal.missing:
        msgs.append(
            f"«{proposal.wallet_name}» está en otra moneda y mencionaste {proposal.moneda}. "
            "¿En qué moneda fue el movimiento?"
        )
    if "wallet" in proposal.missing and not monto_falta:
        msgs.append(f"¿En qué cuenta {verb} ese {proposal.tipo}? {_list_wallets(context)}")
    if "dest_wallet" in proposal.missing:
        msgs.append(f"¿A cuál de tus cuentas {verb} el dinero? {_list_wallets(context)}")
    if "divisa" in proposal.missing:
        msgs.append(_ask_divisa(proposal, context))
    if "tasa" in proposal.missing:
        msgs.append("Falta la tasa: ¿a cuánto el dólar se realizó la operación? (ej.: «30» o «28,5»)")

    return " ".join(msgs) if msgs else "Cuéntame un poco más y lo registro."


def _ask_transfer_confirmation(proposal: ActionProposal, context: dict) -> str:
    """Pide confirmación explícita antes de mover dinero entre cuentas."""
    if proposal.divisa and proposal.tasa:
        monto = f"{proposal.monto:,.2f} {proposal.moneda}" if proposal.moneda else f"{proposal.monto:,.2f}"
        cura, curb = _wallet_currencies(proposal.wallet_name, proposal.dest_wallet_name, context)
        conversion = monto if proposal.moneda else "el monto"
        if cura and curb and cura != curb:
            dest_amount = proposal.monto * proposal.tasa if cura == "USD" else proposal.monto / proposal.tasa
            conversion = f"{dest_amount:,.2f} {curb}"
        return (
            f"Voy a transferir {monto} de «{proposal.wallet_name}» a "
            f"«{proposal.dest_wallet_name}» como **{proposal.divisa} de dólares** "
            f"a la tasa {proposal.tasa:,.2f} (resultado: {conversion}). "
            f"{' · ' + proposal.concepto if proposal.concepto else ''}"
            ' Responde «sí» y la ejecuto (caduca en 10 minutos).'
        )
    return (
        f"Voy a transferir {proposal.monto:,.2f} {proposal.moneda} de "
        f"«{proposal.wallet_name}» a «{proposal.dest_wallet_name}»"
        f"{' · ' + proposal.concepto if proposal.concepto else ''}."
        ' Responde «sí» y la ejecuto (caduca en 10 minutos).'
    )


def _ask_transaction_confirmation(proposal: ActionProposal) -> str:
    """Pide confirmación antes de registrar un cobro o pago."""
    tipo_label = "cobro" if proposal.tipo == "cobro" else "pago"
    monto = f"{proposal.monto:,.2f} {proposal.moneda}"
    wallet_txt = f" en «{proposal.wallet_name}»" if proposal.wallet_name else ""
    concept_txt = f" · Concepto: {proposal.concepto}" if proposal.concepto else ""

    # Conversion details when cross-currency
    conv_txt = ""
    if proposal.convertir and proposal.tasa and proposal.moneda_original:
        from apps.core.currency import round_money as _rm
        if proposal.moneda_original == "USD":
            converted = _rm(proposal.monto * proposal.tasa)
        else:
            converted = _rm(proposal.monto / proposal.tasa)
        wallet_currency = proposal.moneda
        conv_txt = (
            f"\n📐 Conversión: {proposal.monto:,.2f} {proposal.moneda_original} → "
            f"{converted:,.2f} {wallet_currency} "
            f"(tasa {proposal.tipo_tasa or 'personalizada'}: {proposal.tasa})"
        )
        monto = f"{proposal.monto:,.2f} {proposal.moneda_original}"

    return (
        f"Voy a registrar un **{tipo_label}** de {monto}{wallet_txt}{concept_txt}.{conv_txt}"
        ' Responde «sí» y lo registro (caduca en 10 minutos).'
    )


def _complete_or_repeat(
    user,
    context: dict,
    pending_key: str,
    pending: dict,
    message: str,
) -> str:
    """Completa una propuesta pendiente con la respuesta del usuario.

    Si la respuesta aporta el/los datos faltantes (cuenta, monto o moneda) se
    resuelve como un registro nuevo; si no, se repite la pregunta.
    """
    filled = _fill_pending(pending, context, message)
    if filled is None:
        if is_decline(message):
            # El usuario rechazó la oferta («no»): se descarta la propuesta.
            cache.delete(pending_key)
            return (
                "Entendido, no registro nada. "
                "Avísame si necesitas consultar tu balance o registrar algo después."
            )
        return _ask_for(_cached_to_proposal(pending), context)
    if filled.complete:
        return _handle_complete(user, context, filled, pending_key)
    cache.set(pending_key, _proposal_to_cache(filled), PENDING_TTL_SECONDS)
    return _ask_for(filled, context)


def _handle_complete(
    user,
    context: dict,
    proposal: ActionProposal,
    pending_key: str,
) -> str:
    """Resuelve una propuesta completa: cachea y pide confirmación para TODO."""
    if proposal.tipo == "transferencia":
        if not proposal.divisa:
            cura, curb = _wallet_currencies(proposal.wallet_name, proposal.dest_wallet_name, context)
            if cura and curb and cura != curb and not proposal.missing:
                proposal.missing = ["divisa"]
        if "divisa" in proposal.missing:
            cache.set(pending_key, _proposal_to_cache(proposal), PENDING_TTL_SECONDS)
            return _ask_divisa(proposal, context)
        cache.set(pending_key, _proposal_to_cache(proposal, step="confirm"), PENDING_TTL_SECONDS)
        return _ask_transfer_confirmation(proposal, context)

    # Cobros y pagos: ahora también piden confirmación antes de ejecutar.
    cache.set(pending_key, _proposal_to_cache(proposal, step="confirm"), PENDING_TTL_SECONDS)
    return _ask_transaction_confirmation(proposal)


def _fill_pending(pending: dict, context: dict, message: str) -> ActionProposal | None:
    """Rellena los datos faltantes de una propuesta con la respuesta del usuario.

    El usuario contestó la pregunta de Navi (una cuenta, un monto o una
    moneda): se copian los campos que faltan desde el mensaje y se devuelve
    la propuesta completa (o más completa). ``None`` si el mensaje no aporta
    ningún dato útil (cambio de tema, saludo, etc.).
    """
    from apps.assistant import actions as a

    text = a._norm(message)
    if not text:
        return None

    missing = list(pending.get("missing") or [])
    if not missing:
        return None
    touched = False

    monto = pending.get("monto")
    moneda = pending.get("moneda")
    moneda_original = pending.get("moneda_original")
    concepto = pending.get("concepto", "")
    wallet_name = pending.get("wallet_name")
    dest_wallet_name = pending.get("dest_wallet_name")
    tipo = pending.get("tipo")
    divisa = pending.get("divisa")
    tasa = pending.get("tasa")

    if "monto" in missing:
        amt = a._extract_amount(text) or a._extract_plain_amount(text)
        if amt is None:
            written = a._extract_written_amount(text)
            if written is not None:
                amt = (written, None)
        if amt is not None:
            monto = str(amt[0])
            missing.remove("monto")
            touched = True
            if amt[1] and "moneda" in missing:
                moneda = amt[1]
                missing.remove("moneda")
            if (
                tipo == "transferencia"
                and wallet_name
                and dest_wallet_name
                and "divisa" not in missing
            ):
                cura, curb = _wallet_currencies(wallet_name, dest_wallet_name, context)
                if cura and curb and cura != curb:
                    missing.append("divisa")
    elif monto:
        # Ya hay monto anotado, pero el usuario trae OTRO («eran mil quinientos,
        # no dos»): el nuevo monto reemplaza al pendiente (solo en cobros/pagos;
        # en transferencias el monto es parte de la confirmación).
        amt = a._extract_amount(text) or a._extract_plain_amount(text)
        if amt is None:
            written = a._extract_written_amount(text)
            if written is not None:
                amt = (written, None)
        if amt is not None and tipo != "transferencia":
            monto = str(amt[0])
            touched = True

    if "divisa" in missing:
        low = text.lower()
        divisa = None
        for marker in ("venta", "vendi", "vendio", "vendida", "vendido", "sold"):
            if marker in low:
                divisa = "venta"
                break
        if divisa is None:
            for marker in ("compra", "compro", "compre", "comprar", "comprado", "bought"):
                if marker in low:
                    divisa = "compra"
                    break
        if divisa is not None:
            missing.remove("divisa")
            rate = a._extract_plain_amount(text) or a._extract_amount(text)
            if rate is None:
                written = a._extract_written_amount(text)
                if written is not None:
                    rate = (written, None)
            if rate is not None:
                tasa = str(rate[0])
            else:
                missing.append("tasa")
            touched = True

    if "tasa" in missing:
        rate = a._extract_plain_amount(text) or a._extract_amount(text)
        if rate is None:
            written = a._extract_written_amount(text)
            if written is not None:
                rate = (written, None)
        if rate is not None:
            tasa = str(rate[0])
            missing.remove("tasa")
            touched = True

    if "razon" in missing:
        # Si el mensaje trae marcador («El motivo del cobro es X…»), se aísla
        # la frase para que la razón no contamine con el resto de la respuesta
        # (moneda, conversión, etc.); si no, se limpia el mensaje completo.
        motivo = a._reason_phrase(message)
        if motivo is None or not a._has_reason(motivo):
            motivo = a._clean_concept(
                message, context.get("wallets") or [], None, None,
                pending.get("tipo", "pago"),
            )
        if a._has_reason(motivo):
            concepto = motivo
            missing.remove("razon")
            touched = True

    if "moneda" in missing:
        code = extract_currency_code(text)
        if code:
            moneda = code
            missing.remove("moneda")
            touched = True

    if "wallet" in missing or "dest_wallet" in missing:
        wallets = a._match_wallets(context, text)
        if wallets:
            if "wallet" in missing and not wallet_name:
                wallet_name = wallets[0]["name"]
                missing.remove("wallet")
                touched = True
            if "dest_wallet" in missing and not dest_wallet_name:
                dest_wallet_name = wallets[0]["name"]
                missing.remove("dest_wallet")
                touched = True

    if not touched:
        return None

    # Coherencia moneda ↔ billetera al completar (como en ``extract_action``).
    if wallet_name:
        wcur = next(
            (w["currency"] for w in context.get("wallets") or [] if w["name"] == wallet_name),
            None,
        )
        if wcur and "moneda" not in missing:
            if moneda is None:
                moneda = wcur
            elif wcur != moneda:
                missing.append("moneda")

    # La moneda cambió respecto a la que acompañaba el monto ("50 dólares" ->
    # el usuario confirma "bolívares"): hay que convertir con la tasa oficial.
    convertir = bool(
        moneda_original
        and moneda
        and moneda_original != moneda
        and {moneda, moneda_original} == {"USD", "VES"}
    )

    return ActionProposal(
        tipo=tipo,
        monto=Decimal(monto) if monto else None,
        moneda=moneda,
        moneda_original=moneda_original,
        convertir=convertir,
        divisa=divisa,
        tasa=Decimal(tasa) if tasa else None,
        concepto=concepto,
        wallet_name=wallet_name,
        dest_wallet_name=dest_wallet_name,
        missing=missing,
    )


def _wallet_currencies(name_a: str, name_b: str, context: dict) -> tuple[str | None, str | None]:
    """Monedas de dos billeteras por nombre (``(cur_a, cur_b)``)."""
    wallets = {w["name"]: w["currency"] for w in context.get("wallets") or []}
    return wallets.get(name_a), wallets.get(name_b)


def _ask_divisa(proposal: ActionProposal, context: dict) -> str:
    """Pregunta compra/venta + tasa cuando la transferencia cruza monedas."""
    cura, curb = _wallet_currencies(proposal.wallet_name, proposal.dest_wallet_name, context)
    wallet_name = f"«{proposal.wallet_name}» ({cura})" if cura else proposal.wallet_name
    dest_name = f"«{proposal.dest_wallet_name}» ({curb})" if curb else proposal.dest_wallet_name
    return (
        f"Detecto que la transferencia fue en diferentes monedas "
        f"({wallet_name} → {dest_name}). "
        f"¿Fue una venta o compra de divisas y a qué tasa de dólar se realizó "
        f"la transacción? (ej.: «venta a 30», «compra a 28,5»)"
    )


def _list_wallets(context: dict) -> str:
    """Lista legible de billeteras del usuario para cuando hay que elegir."""
    wallets = context.get("wallets") or []
    if not wallets:
        return "No tienes cuentas: créalas primero desde la sección Cuentas."
    names = " · ".join(f"{w['name']} ({w['currency']})" for w in wallets)
    return f"Tus cuentas: {names}."


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------


def _pending_key(user, session_id: uuid.UUID) -> str:
    return f"navi:pending:{user.pk}:{session_id}"


def _proposal_to_cache(proposal: ActionProposal, step: str = "fill") -> dict:
    """Serializa la propuesta para guardarla en cache (JSON-friendly).

    ``step`` indica con qué se espera la próxima respuesta del usuario:
    ``"fill"`` (faltan datos de la operación) o ``"confirm"`` (transferencia
    esperando el «sí» explícito).
    """
    return {
        "tipo": proposal.tipo,
        "monto": str(proposal.monto) if proposal.monto is not None else None,
        "moneda": proposal.moneda,
        "moneda_original": proposal.moneda_original,
        "convertir": proposal.convertir,
        "concepto": proposal.concepto,
        "wallet_name": proposal.wallet_name,
        "dest_wallet_name": proposal.dest_wallet_name,
        "divisa": proposal.divisa,
        "tasa": str(proposal.tasa) if proposal.tasa is not None else None,
        "tipo_tasa": proposal.tipo_tasa,
        "missing": list(proposal.missing),
        "step": step,
    }


def _cached_to_proposal(pending: dict) -> ActionProposal:
    """Reconstruye la propuesta guardada en cache (para repetir la pregunta)."""
    return ActionProposal(
        tipo=pending.get("tipo"),
        monto=Decimal(pending["monto"]) if pending.get("monto") else None,
        moneda=pending.get("moneda"),
        moneda_original=pending.get("moneda_original"),
        convertir=bool(pending.get("convertir")),
        divisa=pending.get("divisa"),
        tasa=Decimal(pending["tasa"]) if pending.get("tasa") else None,
        tipo_tasa=pending.get("tipo_tasa"),
        concepto=pending.get("concepto", ""),
        wallet_name=pending.get("wallet_name"),
        dest_wallet_name=pending.get("dest_wallet_name"),
        missing=list(pending.get("missing") or []),
    )


def _load_history(user, session_id: "uuid.UUID", limit: int = 6) -> list[dict]:
    """Últimos turnos persistidos de la sesión para dar contexto al modelo."""
    try:
        from apps.assistant.models import ChatMessage

        rows = (
            ChatMessage.objects.filter(user=user, session_id=session_id)
            .order_by("-created_at")[: limit * 2]
        )
        ordered = [
            {"role": r.role, "content": r.content}
            for r in reversed(list(rows))
        ]
        return ordered[-limit:]
    except Exception:  # noqa: BLE001 — el historial es best-effort
        return []


def _persist_chat(user, session_id: "uuid.UUID", user_message: str, reply: str) -> None:
    """Persiste el turno (user + assistant) en la sesión (best-effort)."""
    try:
        from apps.assistant.models import ChatMessage

        ChatMessage.objects.create(user=user, session_id=session_id, role="user", content=user_message)
        ChatMessage.objects.create(user=user, session_id=session_id, role="assistant", content=reply)
    except Exception:  # noqa: BLE001 — persistencia best-effort
        logger.exception("No se persistió el mensaje del asistente")


def mock_chat(user, message: str) -> str:
    """Respuesta de demostración (usada en tests y dev sin proveedor)."""
    return MockAssistantProvider().answer(build_context(user), [{"role": "user", "content": message}])


# ---------------------------------------------------------------------------
# Transcripción de voz (chat por voz, iOS y desktop)
# ---------------------------------------------------------------------------


def transcribe(audio: bytes, filename: str) -> dict:
    """Transcribe un clip de voz del usuario usando el proveedor configurado.

    Args:
        audio: bytes del archivo de audio grabado (MediaRecorder).
        filename: nombre original (porta la extensión/content-type).

    Returns:
        Dict ``{"transcript": str}`` con el texto transcrito.
    """
    try:
        transcript = get_transcriber().transcribe(audio, filename)
    except TranscriptionProviderError as exc:
        logger.warning("El proveedor de transcripción falló (%s): %s", exc.code, exc)
        message = PROVIDER_ERROR_MESSAGES.get(exc.code, PROVIDER_ERROR_MESSAGES["provider"])
        raise BusinessRuleError(message) from exc
    except Exception as exc:
        logger.warning("Falló la transcripción de voz: %s", exc)
        raise BusinessRuleError("No pude procesar el audio. Intenta de nuevo.") from exc

    transcript = (transcript or "").strip()
    if not transcript:
        raise BusinessRuleError("No capté lo que dijiste. Intenta de nuevo.")
    return {"transcript": transcript}