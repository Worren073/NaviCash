"""services — Orquestación del asistente Navi.

Flujo de una petición:
1. Validar + persistir el mensaje del usuario (si hay historial activado).
2. Construir el contexto con ``build_context``.
3. Decidir el camino del turno (en este orden):
   a. Intento PELIGROSO (dinero ajeno, borrado, credenciales) → rechazo firme,
      sin tocar el LLM ni la base de datos.
   b. Confirmación de una transferencia pendiente (cache por sesión) → ejecuta.
   c. Registro de cobro/pago/transferencia detectado por ``extract_action``:
      - incompleto → Navi pregunta por los datos faltantes;
      - transferencia → pide confirmación explícita ("sí") antes de mover dinero;
      - cobro/pago → se registra al instante y Navi muestra qué hizo.
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
    extract_action,
    is_confirmation,
    is_dangerous,
)
from apps.assistant.context import build_context
from apps.assistant.intent_rules import answer_deterministic
from apps.assistant.providers import MockAssistantProvider, get_provider
from apps.core.exceptions import BusinessRuleError

logger = logging.getLogger(__name__)

#: TTL de las transferencias pendientes de confirmar (10 minutos).
PENDING_TTL_SECONDS = 600


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

    # 2. Confirmación de una transferencia pendiente.
    elif is_confirmation(message) and pending:
        text = _execute_transfer(user, pending, session_id)
        cache.delete(pending_key)

    # 3. Intento de registro (cobro/pago/transferencia).
    else:
        proposal = extract_action(context, message)
        if proposal is not None:
            if not proposal.complete:
                text = _ask_for(proposal, context)
            elif proposal.tipo == "transferencia":
                cache.set(pending_key, _proposal_to_cache(proposal), PENDING_TTL_SECONDS)
                text = _ask_transfer_confirmation(proposal, context)
            else:
                text = _execute_ledger(user, proposal)

    # 4/5. Respuesta normal: proveedor (LLM con SYSTEM_PROMPT endurecido) o
    # fallback determinista. Las inyecciones de prompt caen aquí: si el LLM
    # está disponible responde endurecido; el fallback sin red las rechaza.
    if text is None:
        provider = get_provider()
        history = _load_history(user, session_id, limit=6)
        try:
            text = provider.answer(context, [*history, {"role": "user", "content": message}])
        except Exception as exc:  # noqa: BLE001 — nunca dejar de responder
            logger.warning("Fallback determinista por error del proveedor: %s", exc)
            text = answer_deterministic(context, message)

    _persist_chat(user, session_id, message, text)
    return {"text": text, "session_id": str(session_id)}


# ---------------------------------------------------------------------------
# Registro de cobros / pagos (ejecución directa)
# ---------------------------------------------------------------------------


def _execute_ledger(user, proposal: ActionProposal) -> str:
    """Registra un cobro/pago claro y devuelve el resumen para el usuario."""
    from apps.transactions.services import register_transaction
    from apps.wallets.models import Wallet

    wallet = None
    if proposal.wallet_name:
        wallet = Wallet.objects.filter(user=user, name=proposal.wallet_name).first()

    try:
        tx = register_transaction(
            user,
            tipo=proposal.tipo,
            monto=proposal.monto,
            moneda=proposal.moneda,
            concepto=proposal.concepto,
            wallet=wallet,
            estado="pagado",
        )
    except BusinessRuleError as exc:
        return (
            f"No pude registrar el {proposal.tipo}: {exc} "
            "Revisa la billetera y la moneda e inténtalo de nuevo."
        )

    return _ledger_confirm_text(tx)


def _ledger_confirm_text(tx) -> str:
    """Resumen legible de un cobro/pago recién registrado."""
    label = "cobro" if tx.tipo == "cobro" else "pago"
    monto = f"{tx.monto:,.2f} {tx.moneda}"
    saldo = f"{tx.wallet.saldo:,.2f} {tx.moneda}" if tx.wallet else "—"
    wallet_txt = f" en «{tx.wallet.name}»" if tx.wallet else ""
    concept_txt = f" · Concepto: {tx.concepto}" if tx.concepto else ""
    return (
        f"✅ Listo. Registré un **{tx.tipo}** de {monto}{wallet_txt}."
        f"{concept_txt}\nTu saldo en esa cuenta quedó en {saldo}."
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
        tx = create_transfer(
            source,
            dest,
            Decimal(pending["monto"]),
            rate_fuente="oficial",
            concepto=pending.get("concepto", ""),
        )
    except BusinessRuleError as exc:
        return f"No pude completar la transferencia: {exc}"

    return _transfer_confirm_text(tx)


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
    wallet_names = " · ".join(w["name"] for w in context.get("wallets") or [])

    msgs = []
    if "monto" in proposal.missing:
        msgs.append(f"¿De cuánto fue el {proposal.tipo}? Dime el monto y lo registro.")
    if "moneda" in proposal.missing:
        msgs.append(
            f"«{proposal.wallet_name}» está en otra moneda y mencionaste {proposal.moneda}. "
            "¿En qué moneda fue el movimiento?"
        )
    if "wallet" in proposal.missing:
        msgs.append(f"¿En qué cuenta {verb} ese {proposal.tipo}? {_list_wallets(context)}")
    if "dest_wallet" in proposal.missing:
        msgs.append(f"¿A cuál de tus cuentas {verb} el dinero? {_list_wallets(context)}")

    return " ".join(msgs) if msgs else "Cuéntame un poco más y lo registro."


def _ask_transfer_confirmation(proposal: ActionProposal, context: dict) -> str:
    """Pide confirmación explícita antes de mover dinero entre cuentas."""
    return (
        f"Voy a transferir {proposal.monto:,.2f} {proposal.moneda} de "
        f"«{proposal.wallet_name}» a «{proposal.dest_wallet_name}»"
        f"{' · ' + proposal.concepto if proposal.concepto else ''}."
        ' Responde «sí» y la ejecuto (caduca en 10 minutos).'
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


def _proposal_to_cache(proposal: ActionProposal) -> dict:
    """Serializa la propuesta para guardarla en cache (JSON-friendly)."""
    return {
        "tipo": proposal.tipo,
        "monto": str(proposal.monto) if proposal.monto is not None else None,
        "moneda": proposal.moneda,
        "concepto": proposal.concepto,
        "wallet_name": proposal.wallet_name,
        "dest_wallet_name": proposal.dest_wallet_name,
    }


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