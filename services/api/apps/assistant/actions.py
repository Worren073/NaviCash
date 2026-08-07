"""actions — Registro de operaciones por chat y guarda de seguridad de Navi.

Esta es la puerta de ENTRADA de escritura del asistente: se ejecuta ANTES de
contactar al LLM y decide si el mensaje del usuario:

- reporta un **cobro / pago / transferencia** entre sus propias cuentas
  (``extract_action``) → Navi pide los datos faltantes o ejecuta el registro
  reutilizando los servicios validados de ``apps.transactions``;
- es un intento **peligroso** (mover dinero a terceros, borrar saldos, lavar
  dinero, revelar credenciales) → rechazo firme, sin llamar al LLM ni a la BD;
- es una **inyección de prompt** (ignorar reglas, cambiar de rol, revelar el
  sistema) → se desvía a una respuesta de rechazo determinista.

Reglas de oro:
- Aquí NUNCA se escribe en la BD: solo se produce una *propuesta* con
  ``ActionProposal``; la ejecución real vive en ``services.chat``.
- Si falta cualquier dato, la propuesta queda ``incomplete`` y Navi pregunta;
  nunca se registra una operación a medias.
- Todo lo de este módulo es determinista y se puede probar sin red ni LLM.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

# ---------------------------------------------------------------------------
# Detección de intenciones de registro
# ---------------------------------------------------------------------------

#: Verbos/frases que reportan un EGRESO (pago). Se buscan en texto normalizado.
PAY_PATTERNS = [
    "gastad", "gaste", "gastar", "gasto ", "comprado", "comprar", "compre",
    "compr", "pague", "pagado", "pagar", "consumi", "consum", "abone",
    "debito", "debit",
]

#: Verbos/frases que reportan un INGRESO (cobro). Van ANTES de los de pago
#: porque frases como "me pagaron" contienen "pag".
COLLECT_PATTERNS = [
    "recib", "cobr", "vend", "ingres", "deposit", "acreditar", "me pagaron",
    "me pago ", "me pago", "me abono", "se me abono", "se me acredito",
]

#: Verbos/frases que reportan una TRANSFERENCIA entre cuentas propias.
TRANSFER_PATTERNS = [
    "transfi", "transfer", "traslad", "traspas", "transferencia",
]

#: Palabras que delatan preguntas de saldo/permiso y NO deben tratarse como
#: registro ("¿me puedo gastar 20$?" es una consulta, no un gasto hecho).
QUESTION_MARKERS = [
    "cuanto", "cuanta", "cuando", "me puedo", "puedo gastar", "me alcanza",
    "me sobra", "me conviene", "me permito", "cuanto me queda", "tengo para",
]

#: Frases que indican que el usuario NO quiere que se registre nada.
NEGATION_MARKERS = [
    "no registres", "no registre", "no lo registres", "no lo hagas",
    "no hagas", "no gastes", "no me cobres", "no me cobra",
]

#: Palabras/frases auxiliares que se recortan del concepto.
CONCEPT_STRIP = [
    "he gastado", "ha gastado", "gastado", "gaste", "gastar", "gasta", "gasto",
    "comprado", "comprando", "comprada", "compre",
    "pagado", "pagar", "pagarlo", "paga", "pague",
    "recibido", "recibir", "recibo", "recibi",
    "cobrado", "cobrar", "cobro", "cobra",
    "vendido", "vender", "venta", "vendi",
    "ingresado", "ingresar", "ingreso",
    "depositado", "depositar", "deposite", "depositaron",
    "acreditado", "acreditar", "acreditaron",
    "transferido", "transferir", "transferencia", "transfiero",
    "trasladado", "trasladar", "pase", "pasado", "abonado", "abone", "consumido",
    "me pagaron", "me pago", "se me abono", "se me acredito",
    "desde mi cuenta", "de mi cuenta", "en mi cuenta", "a mi cuenta",
    "desde la cuenta", "en la cuenta", "de la cuenta", "mi cuenta", "la cuenta",
    "desde mi", "desde", "de mis cuentas",
    "con el fin de", "por concepto de", "concepto",
]

#: Palabras de función que se recortan del inicio del concepto.
CONCEPT_LEADING = [
    "en", "de", "por", "desde", "para", "la", "el", "los", "las", "un",
    "una", "unos", "unas", "con", "a", "y", "he", "lo", "que", "mi", "al",
]

# ---------------------------------------------------------------------------
# Guarda de seguridad (patrones en texto normalizado)
# ---------------------------------------------------------------------------

#: Intentos que se BLOQUEAN sin pasar al LLM: piden acciones sobre dinero ajeno,
#: borrado de datos, lavado o revelar credenciales/sistema.
DANGEROUS_PATTERNS = [
    "olvida tus instrucciones", "olvida tus reglas",
    "ignora tus instrucciones", "ignora tus reglas",
    "no sigas tus instrucciones", "no sigas tus reglas", "desobedece",
    "revela", "prompt de sistema", "prompt del sistema", "system prompt",
    "instrucciones del sistema", "prompt completo", "tu prompt", "dime tu prompt",
    "contraseña", "password", "clave de administrador", "api key", "token de acceso",
    "otra persona", "alguien más", "a otra cuenta", "de otro usuario",
    "otro cliente", "de terceros", "de otra persona", "de mi vecino",
    "blanquea", "lavado de dinero", "hackea", "hacke", "pirate",
    "elimina todas", "borra todas", "borra mi cuenta", "elimina mi cuenta",
    "ponme 1.000.000", "aumenta mi saldo", "modifica mi saldo", "saldo falso",
    "factura falsa", "prestamo sin aprobacion", "préstamo sin aprobación",
    "mueve dinero", "mueve el dinero", "dame acceso", "dame tu clave",
    "no lo registres", "no registres", "no lo anotes", "no lo marques",
]

#: Inyecciones de prompt "blandas": se responden con rechazo determinista
#: cuando el proveedor no está disponible; con LLM se deja la respuesta al
#: modelo (endurecido por el SYSTEM_PROMPT).
INJECTION_PATTERNS = [
    "ignora", "olvida tus", "olvida que", "olvida todo", "no sigas",
    "actua como", "actúa como", "juego de rol", "roleplay", "role play",
    "a partir de ahora", "desde ahora eres", "ahora eres", "cambia tu rol",
    "estas siendo actualizado", "estás siendo actualizado", "eres gpt",
    "eres chatgpt", "eres un modelo de lenguaje", "muestra tu", "cual es tu sistema",
    "cual es tu prompt", "cuál es tu prompt", "dame tu sistema", "repite tu instruccion",
    "repite tus instrucciones", "repite tu contexto", "repite el contexto",
    "confirma que puedes hacerlo", "solo una vez", "sin restricciones",
]

#: Patrones de confirmación de transferencias pendientes ("sí", "dale", ...).
CONFIRMATION_RE = re.compile(
    r"^(s[ií]{1,3}|si\b|confirmo|confirma|confirmad|dale|ok|okay|listo|"
    r"adelante|hazlo|hacelo|acepto|ejecuta|ejecutar|procede)\b",
    re.IGNORECASE,
)

#: RegEx de cantidades: símbolo antes ($250), después (250$) o unidad (250 Bs).
AMOUNT_BEFORE_RE = re.compile(r"(?P<sym>\$\s?|\€\s?)(?P<num>\d[\d.,]*)")
AMOUNT_AFTER_RE = re.compile(
    r"(?P<num>\d[\d.,]*)\s*(?P<unit>usd|d[oó]lares|dolares|bs|bol[íi]vares|"
    r"bolivares|ves|eur|euros)"
)
AMOUNT_TRAILING_RE = re.compile(r"(?P<num>\d[\d.,]*)\s*(?P<sym>[$€])")

#: Unidad → código de moneda.
UNIT_TO_CODE = {
    "usd": "USD", "dólares": "USD", "dolares": "USD", "dolar": "USD",
    "bs": "VES", "bolívares": "VES", "bolivares": "VES", "ves": "VES",
    "eur": "EUR", "euros": "EUR", "euro": "EUR",
}

#: Símbolo → código de moneda.
SYMBOL_TO_CODE = {"$": "USD", "€": "EUR"}

#: Tipo de operación → verbo para las preguntas de Navi.
TIPO_VERB = {
    "pago": "pagaste",
    "cobro": "recibiste",
    "transferencia": "moviste",
}


@dataclass
class ActionProposal:
    """Propuesta de operación extraída del mensaje (nunca toca la BD)."""

    tipo: str  # "pago" | "cobro" | "transferencia"
    monto: "Decimal | None" = None
    moneda: str | None = None
    concepto: str = ""
    wallet_name: str | None = None
    dest_wallet_name: str | None = None
    missing: list[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        """True si hay datos suficientes para ejecutar la propuesta."""
        return not self.missing


def extract_action(context: dict, message: str) -> "ActionProposal | None":
    """Extrae una propuesta de registro (cobro/pago/transferencia) del mensaje.

    Devuelve ``None`` si el mensaje no parece reportar una operación ya
    realizada (preguntas, saludos, etc.).

    Args:
        context: dict plano de ``build_context`` (usa ``wallets`` y
            ``base_currency``).
        message: mensaje original del usuario.

    Returns:
        ``ActionProposal`` con los datos encontrados (puede estar
        ``incomplete``) o ``None`` si no hay intención de registro.
    """
    text = _norm(message)
    if not text:
        return None
    if any(m in text for m in NEGATION_MARKERS):
        return None
    if any(m in text for m in QUESTION_MARKERS):
        return None

    tipo = _detect_tipo(text)
    if tipo is None:
        return None

    wallets = _match_wallets(context, text)

    amount = _extract_amount(text)
    if amount is None:
        # Sin monto no hay registro: puede ser una consulta ("cuánto debo pagar").
        return None

    monto, explicit_code = amount
    currency = explicit_code or _fallback_currency(context, wallets, tipo)

    # Moneda de la billetera vs. moneda del mensaje: si chocan, preguntamos.
    missing: list[str] = []
    if tipo == "transferencia":
        if len(wallets) < 2:
            missing.append("dest_wallet" if wallets else "wallet")
        if currency and wallets:
            _check_currency_match(currency, wallets, missing)
    else:
        if not wallets:
            missing.append("wallet")
        elif currency and wallets:
            _check_currency_match(currency, wallets, missing)

    proposal = ActionProposal(
        tipo=tipo,
        monto=monto,
        moneda=currency,
        concepto=_clean_concept(message, wallets, monto, explicit_code),
        wallet_name=wallets[0]["name"] if wallets else None,
        dest_wallet_name=wallets[1]["name"] if len(wallets) > 1 else None,
        missing=missing,
    )
    return proposal


def is_confirmation(text: str) -> bool:
    """True si el mensaje confirma una transferencia pendiente."""
    return bool(CONFIRMATION_RE.match(_norm(text)))


def is_dangerous(text: str) -> bool:
    """True si el mensaje pide acciones comprometidas (bloqueo total)."""
    norm = _norm(text)
    return any(p in norm for p in DANGEROUS_PATTERNS)


def is_injection(text: str) -> bool:
    """True si el mensaje intenta manipular el rol/reglas del asistente."""
    norm = _norm(text)
    return any(p in norm for p in INJECTION_PATTERNS)


# ---------------------------------------------------------------------------
# Helpers de detección
# ---------------------------------------------------------------------------


def _detect_tipo(text: str) -> str | None:
    """Prioridad: transferencia > cobro > pago (por las frases ambiguas)."""
    if _has_any(text, TRANSFER_PATTERNS):
        return "transferencia"
    if _has_any(text, COLLECT_PATTERNS):
        return "cobro"
    if _has_any(text, PAY_PATTERNS):
        return "pago"
    return None


def _match_wallets(context: dict, text: str) -> list[dict]:
    """Billeteras del usuario mencionadas en el texto (en orden de aparición).

    Devuelve una lista con los dicts ``{"name", "currency", "tipo"}`` de
    ``context["wallets"]`` cuyo nombre (normalizado) aparece en el mensaje.
    """
    wallets = []
    for w in context.get("wallets") or []:
        wname = _norm(w.get("name", ""))
        if wname and wname in text:
            wallets.append(w)
    return wallets


def _extract_amount(text: str) -> "tuple[Decimal, str | None] | None":
    """Primera cantidad del texto y su moneda explícita (si la lleva).

    Returns:
        Tupla ``(monto, code)`` donde ``code`` es la moneda explícita
        (USD/VES/EUR) o ``None`` si el número no trae unidad.
    """
    for match in AMOUNT_BEFORE_RE.finditer(text):
        num = _parse_decimal(match.group("num"))
        if num is not None:
            return num, SYMBOL_TO_CODE.get(match.group("sym").strip(), None)
    for match in AMOUNT_AFTER_RE.finditer(text):
        num = _parse_decimal(match.group("num"))
        if num is not None:
            return num, UNIT_TO_CODE.get(_norm(match.group("unit")), None)
    for match in AMOUNT_TRAILING_RE.finditer(text):
        num = _parse_decimal(match.group("num"))
        if num is not None:
            return num, SYMBOL_TO_CODE.get(match.group("sym"), None)
    return None


def _parse_decimal(raw: str) -> "Decimal | None":
    """Convierte "1.000,50"/"250"/"1,000" a Decimal (None si es inválido)."""
    raw = raw.replace(" ", "")
    try:
        if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", raw):
            return Decimal(raw.replace(",", "").replace(".", ""))
        if "," in raw and "." in raw:
            decimal_sep = "," if raw.rfind(",") > raw.rfind(".") else "."
            thousands_sep = "." if decimal_sep == "," else ","
            return Decimal(raw.replace(thousands_sep, "").replace(decimal_sep, "."))
        if "," in raw:
            return Decimal(raw.replace(",", "."))
        return Decimal(raw)
    except InvalidOperation:
        return None


def _fallback_currency(context: dict, wallets: list[dict], tipo: str) -> str:
    """Moneda por defecto: la de la billetera mencionada o la base del usuario."""
    if wallets:
        return wallets[0]["currency"]
    return context.get("base_currency", "USD")


def _check_currency_match(currency: str, wallets: list[dict], missing: list[str]) -> None:
    """Si la moneda del mensaje choca con la de la billetera, pedimos aclarar."""
    for w in wallets:
        if w.get("currency") != currency:
            missing.append("moneda")
            break


def _clean_concept(
    message: str,
    wallets: list[dict],
    monto: "Decimal | None" = None,
    explicit_code: str | None = None,
) -> str:
    """Reduce el mensaje a un concepto: recorta verbos, cuentas y montos."""
    concept = message
    lowered = _norm(concept)

    for phrase in CONCEPT_STRIP:
        concept = re.sub(rf"\b{re.escape(phrase)}\b", " ", concept, flags=re.IGNORECASE)

    for w in wallets:
        concept = re.sub(
            rf"\b{re.escape(w['name'])}\b", " ", concept, flags=re.IGNORECASE
        )

    if monto is not None:
        concept = re.sub(r"\d[\d.,]*", " ", concept)
        for unit in ("usd", "dólares", "dolares", "bs", "bolívares", "bolivares", "ves"):
            concept = re.sub(rf"\b{unit}\b", " ", concept, flags=re.IGNORECASE)
        concept = concept.replace("$", " ").replace("€", " ")

    concept = _collapse(concept)
    while concept:
        lead = re.match(rf"\b(?:{'|'.join(re.escape(w) for w in CONCEPT_LEADING)})\b", concept, re.IGNORECASE)
        if not lead:
            break
        concept = _collapse(concept[lead.end():])
    concept = concept.strip(" .,;:·–-—")
    return concept[:1].upper() + concept[1:] if concept else ""


def _collapse(text: str) -> str:
    """Colapsa espacios y signos repetidos."""
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s*([,;.:])\s*", r"\1 ", text)
    return text.strip()


def _has_any(text: str, patterns: list[str]) -> bool:
    return any(p in text for p in patterns)


def _norm(text: str) -> str:
    """Minúsculas, sin acentos y con espacios colapsados (para matching)."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text.lower().strip())


# ---------------------------------------------------------------------------
# Textos de rechazo (usados por intent_rules y services)
# ---------------------------------------------------------------------------


def answer_dangerous() -> str:
    """Rechazo firme ante intentos que comprometen el dinero o los datos."""
    return (
        "⚠️ Eso no lo puedo hacer. NaviCash solo registra cobros, pagos y "
        "transferencias entre tus propias cuentas, y nunca ejecuto movimientos "
        "ni expongo credenciales o datos sensibles. "
        "Cuéntame el movimiento real que quieres registrar y lo anoto por ti 😊."
    )


def answer_injection() -> str:
    """Rechazo ante intentos de inyectar instrucciones o cambiar el rol."""
    return (
        "No puedo hacer eso: mis instrucciones y el contexto son internos y no "
        "se revelan, y no cambio mi rol a pedido. Si tienes dudas sobre tu "
        "dinero, dime qué necesitas y te ayudo con tu información 😊."
    )
