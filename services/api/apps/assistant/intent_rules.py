"""intent_rules — Respuesta determinista (fallback sin red) de Navi.

Estas reglas se usan cuando el proveedor de LLM no está configurado o falla
(Fase 1). Cubren los intents que ya implementa el frontend de forma local para
que el backend -con el mismo contexto- pueda responder de forma consistente:

- saldo / balance / cuanto tengo
- cobrar / por cobrar (pendientes vencidos por recibir)
- pagar / deudas / vencidos (pendientes por pagar)
- ahorro / metas (avance y total ahorrado)
- mensualidades / suscripciones
- próximo vencimiento
- "¿me puedo permitir X?" (regla simple: comparar gasto vs precional de la
  billetera/ahorro)

Todas las respuestas usan SOLO el ``context`` pasado en llamada; nunca
consultan a la base de datos ni exponen datos que no estén en el contexto.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from apps.assistant.actions import answer_dangerous, answer_injection, is_dangerous, is_injection

#: Unidades (solo context, decimal libre).
USD = "USD"


def answer_deterministic(context: dict, user_text: str) -> str:
    """Responde de forma determinista según el texto del usuario y el contexto.

    Args:
        context: dict plano con el estado agregado del usuario.
        user_text: último mensaje del usuario (minúsculas).

    Returns:
        Texto de la respuesta en español.
    """
    text = (user_text or "").lower()

    # Guarda de seguridad: los intentos comprometidos/inyección se rechazan
    # antes de llegar a cualquier intent de información.
    if is_dangerous(text):
        return answer_dangerous()
    if is_injection(text):
        return answer_injection()

    if _has(text, ["permitir", "permito", "gastar", "comprar", "puedo gastar", "me alcanza", "me sobra"]):
        return _answer_afford(context, text)

    if _has(text, ["saldo", "balance", "cuanto tengo", "cuanto dinero", "plata tengo", "dinero tengo", "billetera", "cuenta"]):
        return _answer_balance(context)

    if _has(text, ["por cobrar", "cobrar", "cobrarme", "recibir", "a favor", "me deben", "deben"]):
        return _answer_to_receive(context)

    if _has(text, ["por pagar", "pagar", "deudas", "debo", "vencido", "vencida", "vencidos", "pendiente", "atrasado", "pagar"]):
        return _answer_to_pay(context)

    if _has(text, ["ahorro", "metas", "meta", "ahorrar", "ahorrado", "fondo"]):
        return _answer_goals(context)

    if _has(text, ["mensualidad", "mensualidades", "suscripcion", "subscription", "streaming", "netflix", "spotify", "gimnasio"]):
        return _answer_subscriptions(context)

    if _has(text, ["proximo", "proxim", "siguiente", "vencido", "cuando vence", "que vence", "vence"]):
        return _answer_upcoming(context)

    return _answer_generic(context)


def _answer_generic(context: dict) -> str:
    """Respuesta de respaldo cuando el texto no casa con ningún intent."""
    bal = _fmt(context.get("total_balance_usd"))
    return (
        "Puedo ayudarte con tu dinero 😊. dime por ejemplo: "
        f"«¿Cuánto tengo?» (saldo: {bal} USD), «¿Qué me deben?», "
        "«¿Cuánto debo?», «Mis metas de ahorro», «Mis mensualidades» o "
        "«¿Me lo puedo permitir?»."
    )


def _answer_balance(context: dict) -> str:
    """Saldo global en USD y en moneda local si hay tasa."""
    bal = _decimal(context.get("total_balance_usd"))
    ves = _decimal_opt(context.get("total_balance_ves"))
    msg = f"Tu saldo total es {bal:,.2f} USD"
    if ves is not None:
        msg += f" (más o menos {ves:,.2f} VES)"
    wallets = context.get("wallets") or []
    if wallets:
        names = " · ".join(f"{w['name']}: {_fmt(w['saldo'])} {w['currency']}" for w in wallets)
        msg += f"\nDesglose: {names}"
    return msg


def _answer_to_receive(context: dict) -> str:
    """Cobros pendientes vencidos."""
    amount = _decimal(context.get("to_receive"))
    if amount <= 0:
        return "No tienes cobros pendientes de cobro. Todo cuadrado por ese lado 🎉."
    return (
        f"Tienes {amount:,.2f} {context.get('base_currency', 'USD')} por cobrar "
        "(cobros vencidos). Echa un vistazo a la sección de operaciones pendientes."
    )


def _answer_to_pay(context: dict) -> str:
    """Pagos pendientes vencidos + totales atrasados."""
    amount = _decimal(context.get("to_pay"))
    if amount <= 0:
        return "No tienes pagos vencidos por ahora. ¡Todo al día! 🎉"
    return (
        f"Tienes {amount:,.2f} {context.get('base_currency', 'USD')} por pagar "
        "(pagos vencidos). Tómalo con calma y revisá tus operaciones pendientes 😉."
    )


def _answer_goals(context: dict) -> str:
    """Metas de ahorro con su progreso."""
    goals = context.get("goals") or []
    if not goals:
        return "No tienes metas de ahorro registradas todavía. Crea una en la sección Ahorro."
    lines = [
        f"- «{g['name']}»: {g['progress_percent']}% del objetivo ({_fmt(g['total_contributed'])} "
        f"{g['currency']} aportados de {_fmt(g['target_amount'])} {g['currency']})"
        for g in goals
    ]
    total = _decimal(context.get("savings_total_usd"))
    head = f"Tienes {len(goals)} meta(s) de ahorro:\n" + "\n".join(lines)
    if total > 0:
        head += f"\nTotal ahorrado en cuentas de ahorro: {_fmt(total)} USD"
    return head


def _answer_subscriptions(context: dict) -> str:
    """Mensualidades listadas con días restantes."""
    subs = context.get("subscriptions") or []
    if not subs:
        return "No tienes mensualidades registradas. Puedes agregar una desde la sección Mensualidades."
    lines = []
    for s in subs:
        if s["status"] == "finalizada":
            st = "finalizada ⏰"
        elif s["status"] == "activa":
            st = f"activa · restan {s['days_remaining']} días"
        else:
            st = f"próxima (empieza en {s['days_total'] - s['days_remaining']} días)" if s["days_total"] else "próxima"
        lines.append(f"«{s['name']}» — {st}")
    return "Tus mensualidades:\n" + "\n".join(lines)


def _answer_upcoming(context: dict) -> str:
    """Próximos vencimientos pendientes (de la lista ``upcoming``)."""
    upcoming = context.get("upcoming") or []
    if not upcoming:
        return "No tienes operaciones próximas a vencer. Todo tranquilo 😌."
    lines = [
        f"«{t['concepto']}» {t['monto']} {t['moneda']} — vence el {t['fecha_vencimiento']}"
        for t in upcoming[:5]
    ]
    return "Tus próximos vencimientos:\n" + "\n".join(lines)


def _answer_afford(context: dict, text: str) -> str:
    """Respuesta para "¿puedo gastar X?": compara X vs presupuesto flujo."""
    amount = _first_decimal(text)
    if amount is None:
        return (
            "Para decirte si puedes gastarlo dime una cantidad, por ejemplo "
            "«¿me puedo gastar 20 dólares?»"
        )
    # Presupuesto simple: ingreso del mes - gastos del mes (net).
    net = _decimal(context.get("fin_month", {}).get("net"))
    if net is None:
        net = Decimal("0")
    if amount <= net:
        return (
            f"Sí, {_fmt(amount)} USD entra en tu flujo del mes "
            f"(ingresos − gastos = {_fmt(net)} USD). ¡Dale!"
        )
    bal = _decimal(context.get("total_balance_usd"))
    if amount <= bal:
        return (
            f"{_fmt(amount)} USD supera tu flujo del mes ({_fmt(net)} USD), pero "
            f"tu saldo total es {_fmt(bal)} USD; podrías, pero revisá que no te "
            "deje corto para tus compromisos."
        )
    return (
        f"{_fmt(net)} {USD} de flujo mensual y {_fmt(amount)} USD gasto no te "
        "sugiero: te pasaría del flujo del mes. Buscá alternativas o un plan de ahorro."
    )


# --- utilidades de formato y parseo --------------------------------------


def _fmt(value) -> str:
    """Formatea un decimal/str a cifra con separador de miles."""
    return f"{_decimal(value):,.2f}"


def _decimal(value) -> Decimal:
    """Convierte a Decimal de forma segura (0 si falla)."""
    if value is None:
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _decimal_opt(value) -> "Decimal | None":
    """Como ``_decimal`` pero devuelve ``None`` cuando es ``None``."""
    if value is None:
        return None
    return _decimal(value)


def _first_decimal(text: str) -> "Decimal | None":
    """Primera cantidad numérica en el texto (con/sin punto decimal)."""
    match = re.search(r"\d[\d\.,]*", text)
    if not match:
        return None
    raw = match.group(0).replace(",", "").replace(".", ".")
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


def _has(text: str, patterns: list[str]) -> bool:
    """True si el texto contiene alguno de los patrones (minúsculas)."""
    lowered = text.lower()
    return any(p.lower() in lowered for p in patterns)