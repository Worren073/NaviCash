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

Si ``context["view"] == "business"`` se usan las reglas de negocio (flujo de
caja, por cobrar/pagar, inventario, margen y mejores clientes) sobre el
contexto del negocio.
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

    # Vista de NEGOCIO: reglas deterministas propias (asesor de negocio).
    if context.get("view") == "business":
        return _answer_business(context, text)

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


# --- Vista de NEGOCIO -------------------------------------------------------


def _answer_business(context: dict, text: str) -> str:
    """Respuesta determinista para la vista de negocio (asesor, solo lectura)."""
    if not context.get("business"):
        return (
            "Aún no tienes un negocio creado en NaviCash. Créalo desde la "
            "sección Negocio y podré analizarte tu flujo de caja, tus cobros, "
            "tus pagos y tu inventario."
        )

    if _has(text, ["cobrar", "por cobrar", "me deben", "recibir", "cartera", "factura"]):
        return _answer_business_receivables(context)
    if _has(text, ["pagar", "por pagar", "debo", "proveedor", "pedido"]):
        return _answer_business_payables(context)
    if _has(text, ["inventario", "stock", "producto", "existencias", "repon"]):
        return _answer_business_inventory(context)
    if _has(text, ["margen", "rentabilidad", "ganancia", "utilidad", "flujo", "vend", "ingres", "gast"]):
        return _answer_business_cashflow(context)
    if _has(text, ["cliente", "mejor", "top", "vende más", "factura más"]):
        return _answer_business_top_clients(context)
    if _has(text, ["saldo", "balance", "cuanto tengo", "dinero", "caja", "cuenta"]):
        return _answer_business_balance(context)

    return _answer_business_generic(context)


def _answer_business_generic(context: dict) -> str:
    """Respaldo de negocio: qué puede hacer Navi en esta vista."""
    name = (context.get("business") or {}).get("name", "tu negocio")
    return (
        f"Puedo analizar {name} y darte recomendaciones 😊. Pregúntame por tu "
        "flujo de caja, tus cuentas por cobrar o por pagar, tu cartera vencida, "
        "tu inventario o tu margen. Recuerda que soy una IA: mis recomendaciones "
        "son orientativas y no sustituyen a un contador o asesor profesional."
    )


def _answer_business_balance(context: dict) -> str:
    """Saldo del negocio + flujo del mes."""
    saldo = _fmt(context.get("saldo"))
    currency = context.get("currency", "USD")
    income = context.get("ingresos_mes")
    expenses = context.get("egresos_mes")
    msg = f"El saldo de tu negocio es {saldo} {currency}."
    if income is not None and expenses is not None:
        msg += (
            f" Este mes llevas {_fmt(income)} {currency} en ingresos y "
            f"{_fmt(expenses)} {currency} en egresos."
        )
    return msg


def _answer_business_cashflow(context: dict) -> str:
    """Flujo de caja: ingresos/egresos del período y margen."""
    kpis = context.get("kpis") or {}
    currency = context.get("currency", "USD")
    income = _decimal(kpis.get("incomePeriod"))
    expense = _decimal(kpis.get("expensePeriod"))
    net = income - expense
    msg = (
        f"En el período registraste {income:,.2f} {currency} de ingresos y "
        f"{expense:,.2f} {currency} de egresos (neto {net:,.2f} {currency})."
    )
    margin = kpis.get("marginPct")
    if margin is not None:
        msg += f" Tu margen es de {margin}%."
        if _decimal(margin) < 10:
            msg += " Es bajo: revisa tus costos y precios de venta."
    return msg


def _answer_business_receivables(context: dict) -> str:
    """Cuentas por cobrar y cartera vencida."""
    kpis = context.get("kpis") or {}
    currency = context.get("currency", "USD")
    receivable = _decimal(kpis.get("receivable"))
    overdue = _decimal(kpis.get("overdue"))
    open_inv = context.get("open_invoices") or {}
    msg = (
        f"Tienes {receivable:,.2f} {currency} por cobrar en "
        f"{open_inv.get('count', 0)} factura(s) abierta(s)."
    )
    if overdue > 0:
        msg += (
            f" De eso, {overdue:,.2f} {currency} está vencido: te recomiendo "
            "priorizar la cobranza de esas facturas."
        )
    return msg


def _answer_business_payables(context: dict) -> str:
    """Cuentas por pagar y pedidos pendientes."""
    kpis = context.get("kpis") or {}
    currency = context.get("currency", "USD")
    payable = _decimal(kpis.get("payable"))
    orders = context.get("pending_orders") or {}
    return (
        f"Tienes {payable:,.2f} {currency} por pagar en "
        f"{orders.get('count', 0)} pedido(s) con saldo pendiente."
    )


def _answer_business_inventory(context: dict) -> str:
    """Inventario: valor, número de productos y stock bajo."""
    inventory = context.get("inventory") or {}
    currency = context.get("currency", "USD")
    low = context.get("low_stock") or []
    msg = (
        f"Tu inventario tiene {inventory.get('product_count', 0)} producto(s) "
        f"por un valor de {_fmt(inventory.get('total_value'))} {currency} a costo."
    )
    if low:
        names = " · ".join(f"{p['name']} ({p['stock_quantity']} {p['unit']})" for p in low[:5])
        msg += f" ⚠️ {len(low)} con stock bajo: {names}. Conviene reponerlos."
    return msg


def _answer_business_top_clients(context: dict) -> str:
    """Mejores clientes (y proveedores) del período."""
    clients = context.get("top_clients") or []
    if not clients:
        return "Aún no hay pagos de clientes en el período para destacar."
    currency = context.get("currency", "USD")
    names = " · ".join(f"{c['label']}: {_fmt(c['value'])} {currency}" for c in clients[:5])
    return "Tus mejores clientes del período:\n" + names


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