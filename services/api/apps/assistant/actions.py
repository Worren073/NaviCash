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
    "compr", "pague", "pagado", "pagar", "pago", "pagaste", "consumi",
    "consum", "abone", "debito", "debit",
]

#: Verbos/frases que reportan un INGRESO (cobro). Van ANTES de los de pago
#: porque frases como "me pagaron" contienen "pag".
COLLECT_PATTERNS = [
    "recib", "cobr", "vend", "ingres", "deposit", "acreditar",
    "me pagaron", "me pago ", "me pago", "me abono", "se me abono",
    "se me acredito", "acaban de pagar", "acaban de depositar",
    "acaban de abonar", "me acaba de pagar", "me acaba de depositar",
    "me acaba de abonar", "me acaban de pagar", "me acaban de depositar",
    "me acaban de abonar",
]

#: Verbos/frases que reportan una TRANSFERENCIA entre cuentas propias.
TRANSFER_PATTERNS = [
    "transfi", "transfer", "traslad", "traspas", "transferencia",
]

#: Formas que reportan un movimiento YA realizado pero SIN monto ("Acabo de
#: comprar un café") → activan la oferta de Navi de registrarlo.
SPENT_REPORT_PATTERNS = [
    "acabo de comprar", "acabas de comprar", "acabamos de comprar",
    "acabo de pagar", "acabas de pagar", "acabamos de pagar",
    "acabo de gastar", "acabas de gastar", "acabe de comprar",
    "acabe de pagar", "acabo de abonar", "acabamos de gastar",
    "compre ", "compramos", "compraron", "compre un", "compre una",
    "pague ", "pagamos", "pagaron", "pague el", "pague la", "pague un",
    "gaste ", "gaste en", "gaste el", "gaste la", "gaste un", "gaste una",
]

#: Formas pasadas de INGRESO sin monto ("cobré el alquiler", "me pagaron…").
PAST_COLLECT_MARKERS = [
    "recibi ", "recibi el", "recibi la", "recibi un", "recibi mi",
    "cobre ", "cobre el", "cobre la", "cobre un", "cobre mi", "cobre por",
    "me pagaron", "me depositaron", "me abonaron", "me acreditaron",
    "se me acredito", "vendi ", "vendí ", "vendi mi", "vendi el",
    "vendi la", "vendi un", "cobre en",
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

#: Partículas que se ignoran al comparar nombres de billeteras
#: ("Banco de Venezuela" ≈ "Banco Venezuela").
WALLET_STOPWORDS = {
    "de", "del", "la", "el", "los", "las", "mi", "mis", "cuenta", "cuentas",
    "y", "a", "en", "mi",
}

#: Palabras/frases auxiliares que se recortan del concepto.
#: Las frases compuestas van PRIMERO: recortar "pagar" o "depositar" antes
#: rompería "me acaban de pagar" o "acaban de depositar".
CONCEPT_STRIP = [
    "me acaban de pagar", "me acaban de depositar", "me acaban de abonar",
    "me acaba de pagar", "me acaba de depositar", "me acaba de abonar",
    "acaban de pagar", "acaban de depositar", "acaban de abonar",
    "me pagaron", "me pago", "me deposito", "me depositaron",
    "se me abono", "se me acredito", "me acreditaron",
    "he gastado", "ha gastado", "gastado", "gaste", "gastar", "gasta", "gasto",
    "comprado", "comprando", "comprada", "compre",
    "pagado", "pagar", "pagarlo", "paga", "pague",
    "recibido", "recibir", "recibo", "recibi",
    "cobrado", "cobrar", "cobro", "cobra",
    "vendido", "vender", "vendi",
    "ingresado", "ingresar", "ingreso",
    "depositado", "depositar", "deposite", "depositaron",
    "acreditado", "acreditar", "acreditaron",
    "transferido", "transferir", "transferencia", "transfiero",
    "trasladado", "trasladar", "pase", "pasado", "abonado", "abone", "consumido",
    "me pagaron", "me pago", "se me abono", "se me acredito",
    "quiero registrar", "quiero registrar el", "registrar", "registra",
    "registrarme", "registra el", "anotar", "anota", "registra el pago",
    "el pago", "el gasto", "un pago", "un gasto", "de 250",
    "acabo de", "acaba de", "acaban de", "acabamos de", "acabe de",
    "desde mi cuenta", "de mi cuenta", "en mi cuenta", "a mi cuenta",
    "desde la cuenta", "en la cuenta", "de la cuenta", "mi cuenta", "la cuenta",
    "desde mi", "desde", "de mis cuentas",
    "con el fin de", "por concepto de", "concepto",
]

#: Palabras de función que se recortan del inicio del concepto.
CONCEPT_LEADING = [
    "en", "de", "por", "desde", "para", "la", "el", "los", "las", "un",
    "una", "unos", "unas", "con", "a", "y", "he", "lo", "que", "mi", "al",
    "fue", "era", "es", "eso", "esto",
]

#: Restos de frase que NO son una razón: quedan tras recortar los verbos
#: cuando el usuario no dijo el motivo ("Navi me acaban de pagar…" → "Navi").
RESIDUAL_WORDS = {
    "navi", "acabo", "acaba", "acaban", "acabamos", "acabe",
    "listo", "ok", "okay", "dale", "sipo", "pago", "cobro", "gasto",
    "registrado", "registro", "ingreso", "egreso",
}

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
    moneda_original: str | None = None  # moneda con la que se dijo el monto
    convertir: bool = False  # convertir el monto a la moneda de la cuenta
    divisa: str | None = None  # "venta" | "compra" en transferencias inter-monedas
    tasa: "Decimal | None" = None  # tasa USD manual declarada por el usuario
    concepto: str = ""
    wallet_name: str | None = None
    dest_wallet_name: str | None = None
    missing: list[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        """True si hay datos suficientes para ejecutar la propuesta."""
        return not self.missing


def _offer_without_amount(tipo: str, text: str, wallets: list[dict]) -> "ActionProposal | None":
    """Propuesta sin monto para un movimiento reportado sin cantidad.

    "Acabo de comprar un café" no trae cuánto pagó, pero sí la intención;
    igual "Acabo de realizar una transferencia de mi cuenta X a mi cuenta Y"
    no dice cuánto movió: se devuelve una propuesta incompleta (solo falta
    monto y quizá cuenta) para que Navi ofrezca registrarlo en vez de
    responder genérico.

    Returns:
        ``ActionProposal`` incompleto (missing=["monto"] y "wallet" si no
        hay cuenta mencionada) o ``None`` si el tipo no admite el registro
        o el mensaje no reporta un movimiento concreto.
    """
    if tipo not in ("pago", "cobro", "transferencia"):
        return None
    # Solo cuando el texto deja claro que el movimiento YA ocurrió
    # (verbos en pasado / "acabo de"): un deseo futuro ("quiero comprar",
    # "voy a transferir") no debe disparar la oferta.
    if _has_any(text, [" quiero ", "quisiera ", " me gustaria ", "voy a comprar", "voy a pagar", "voy a transferir", "transferire", "transferiré", "compraré", "pagare", "pagare el"]):
        return None
    if tipo in ("pago", "cobro") and not _has_any(text, SPENT_REPORT_PATTERNS + PAST_COLLECT_MARKERS):
        return None

    concepto = _clean_concept(text, wallets, None, None, tipo)
    proposal = ActionProposal(
        tipo=tipo,
        monto=None,
        moneda=None,
        concepto=concepto,
        wallet_name=wallets[0]["name"] if wallets else None,
        dest_wallet_name=wallets[1]["name"] if len(wallets) > 1 else None,
        missing=["monto"],
    )
    if tipo == "transferencia":
        if len(wallets) < 2:
            proposal.missing.append("dest_wallet" if wallets else "wallet")
    elif not wallets:
        proposal.missing.append("wallet")
    return proposal


def is_decline(text: str) -> bool:
    """True si el usuario rechaza la oferta de registro («no», «olvídalo»).

    Solo respuestas cortas de rechazo: un «no» con datos ("no fue en Banesco")
    no cuenta como rechazo porque sigue completando la propuesta.
    """
    t = _norm(text.replace(",", " ").replace(".", " "))
    if t in {"no", "nop", "no quiero", "no gracias", "no hace falta",
             "no registres", "olvidalo", "olvida", "dejalo", "déjalo"}:
        return True
    return any(t.startswith(p) for p in ("no quiero", "no gracias", "no hace"))


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

    # Monto: primero con moneda explícita; si no, cualquier número del texto
    # (la moneda se deduce de la billetera o de la base del usuario).
    amount = _extract_amount(text)
    if amount is None:
        plain = _extract_plain_amount(text)
        if plain is None:
            written = _extract_written_amount(text)
            if written is None:
                # Sin monto: si el mensaje reporta un gasto/cobro hecho
                # ("Acabo de comprar un café"), Navi ofrece registrar; las
                # consultas sin movimiento ("cuánto debo pagar") ya quedaron
                # fuera arriba.
                return _offer_without_amount(tipo, text, wallets)
            monto, explicit_code = written, None
        else:
            monto, explicit_code = plain
    else:
        monto, explicit_code = amount
    currency = explicit_code or extract_currency_code(text) or _fallback_currency(context, wallets, tipo)
    # Si el usuario dijo la moneda del monto ("50 dólares"), se guarda para
    # poder convertir al confirmarse una cuenta en otra moneda.
    moneda_original = explicit_code

    # Moneda de la billetera vs. moneda del mensaje: si chocan, preguntamos.
    # (En transferencias la moneda NO se pregunta: el movimiento usa la de
    # cada cuenta y, si entre ambas difieren, Navi pregunta compra/venta y la
    # tasa al confirmar.)
    missing: list[str] = []
    if tipo == "transferencia":
        if len(wallets) < 2:
            missing.append("dest_wallet" if wallets else "wallet")
    else:
        if not wallets:
            missing.append("wallet")
        elif currency and wallets:
            _check_currency_match(currency, wallets, missing)

    concepto = _clean_concept(message, wallets, monto, explicit_code, tipo)

    # Razón del cobro/pago: si el mensaje no la trae clara, se pregunta
    # ("Navi me acaban de pagar 25000 Bs…" no dice para qué).
    if tipo in ("pago", "cobro") and not _has_reason(concepto):
        missing.append("razon")

    proposal = ActionProposal(
        tipo=tipo,
        monto=monto,
        moneda=currency,
        moneda_original=moneda_original,
        concepto=concepto,
        wallet_name=wallets[0]["name"] if wallets else None,
        dest_wallet_name=wallets[1]["name"] if len(wallets) > 1 else None,
        missing=missing,
    )
    return proposal


def is_confirmation(text: str) -> bool:
    """True si el mensaje confirma una transferencia pendiente."""
    return bool(CONFIRMATION_RE.match(_norm(text)))


def extract_currency_code(text: str) -> str | None:
    """Código de moneda mencionado en una respuesta breve ("en usd", "250 bs").

    Sirve para completar propuestas pendientes cuando el usuario responde la
    pregunta de Navi con solo la moneda.
    """
    t = _norm(text)
    for match in AMOUNT_AFTER_RE.finditer(t):
        code = UNIT_TO_CODE.get(_norm(match.group("unit")))
        if code:
            return code
    if "€" in t:
        return "EUR"
    if "$" in t:
        return "USD"
    if re.search(r"\b(?:usd|dolares|dólares|dolar)\b", t):
        return "USD"
    if re.search(r"\b(?:ves|bolivares|bolívares)\b", t):
        return "VES"
    return None


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

    La comparación ignora partículas ("Banco de Venezuela" se reconoce aunque
    el mensaje diga "banco venezuela" o viceversa): primero se exige que todos
    los tokens significativos del nombre estén en el mensaje; si nada cuadra,
    se acepta la billetera con mayor solape de tokens ("cuenta de venezuela"
    → "Banco de Venezuela").

    Returns:
        Lista con los dicts ``{"name", "currency", "tipo"}`` de
        ``context["wallets"]`` que coinciden, en orden de aparición.
    """
    found = []
    for w in context.get("wallets") or []:
        tokens = _wallet_tokens(w.get("name", ""))
        if tokens and all(t in text for t in tokens):
            found.append(w)

    if not found:
        best, best_n = None, 0
        for w in context.get("wallets") or []:
            tokens = _wallet_tokens(w.get("name", ""))
            n = sum(1 for t in tokens if t in text)
            if n > best_n:
                best, best_n = w, n
        if best is not None:
            found.append(best)

    def first_index(w: dict) -> int:
        positions = [text.find(t) for t in _wallet_tokens(w["name"]) if text.find(t) != -1]
        return min(positions) if positions else len(text)

    found.sort(key=first_index)
    return found


def _wallet_tokens(name: str) -> list[str]:
    """Tokens significativos del nombre de una billetera (sin partículas)."""
    return [t for t in _norm(name).split() if t not in WALLET_STOPWORDS and len(t) > 1]


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


# ---------------------------------------------------------------------------
# Montos escritos con palabras ("Dos dólares", "mil quinientos bolívares")
# ---------------------------------------------------------------------------

#: Números en español (normalizados sin tildes). "un/uno/una" quedan fuera:
#: son ambigüos en frases como "compré una licuadora", que no trae cantidad.
_SPANISH_UNITS = {
    "cero": 0, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6,
    "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12,
    "trece": 13, "catorce": 14, "quince": 15,
}
_SPANISH_TENS = {
    "dieciseis": 16, "diecisiete": 17, "dieciocho": 18, "diecinueve": 19,
    "veinte": 20, "veinti": 20,
    "treinta": 30, "cuarenta": 40, "cincuenta": 50, "sesenta": 60,
    "setenta": 70, "ochenta": 80, "noventa": 90,
}
_SPANISH_HUNDREDS = {
    "cien": 100, "ciento": 100, "doscientos": 200, "trescientos": 300,
    "cuatrocientos": 400, "quinientos": 500, "seiscientos": 600,
    "setecientos": 700, "ochocientos": 800, "novecientos": 900,
}
_SPANISH_GROUPS = {"mil": 1000, "millon": 1_000_000, "millones": 1_000_000}


def _spanish_token_value(token: str) -> int | None:
    """Valor numérico de un token en español, o None si no es numérico."""
    if token in _SPANISH_UNITS:
        return _SPANISH_UNITS[token]
    if token in _SPANISH_TENS:
        return _SPANISH_TENS[token]
    if token in _SPANISH_HUNDREDS:
        return _SPANISH_HUNDREDS[token]
    if token in _SPANISH_GROUPS:
        return _SPANISH_GROUPS[token]
    if token.startswith("veinti"):
        # "veintiuno...veintinueve" = 20 + unidad (el resto ya se quitó).
        rest = token[len("veinti"):]
        if rest in _SPANISH_UNITS:
            return 20 + _SPANISH_UNITS[rest]
    return None


def _words_to_number(tokens: list[str]) -> int | None:
    """Convierte una secuencia de palabras numéricas a un entero.

    Soporta el esquema clásico: unidades, decenas, centenas y grupos de mil
    ("dos mil quinientos treinta" → 2530). ``None`` si la combinación no se
    interpreta.
    """
    total, current = 0, 0
    for token in tokens:
        if token == "y":
            continue
        value = _spanish_token_value(token)
        if value is None:
            return None
        if value in (1000, 1_000_000):
            current = current or 1
            if value == 1000:
                total += current * value
            else:
                total = (total + current) * value
            current = 0
        elif value >= 100:
            current = current * 100 + value if current >= 100 else value
        else:
            current += value
    return total + current if total or current else None


def _extract_written_amount(text: str) -> Decimal | None:
    """Primer monto escrito en palabras ("dos mil quinientas…").

    Returns:
        ``Decimal`` con la cantidad, o ``None`` si no hay número en letras.
    """
    tokens = _norm(text).split()
    for i, token in enumerate(tokens):
        if _spanish_token_value(token) is None and token != "y":
            continue
        seq: list[str] = []
        while i < len(tokens) and (
            tokens[i] == "y" or _spanish_token_value(tokens[i]) is not None
        ):
            seq.append(tokens[i])
            i += 1
        if len(seq) - seq.count("y") >= 1:
            value = _words_to_number(seq)
            if value is not None and value > 0:
                return Decimal(str(value))
    return None


def _extract_plain_amount(text: str) -> "tuple[Decimal, None] | None":
    """Primera cantidad sin moneda explícita ("gasté 250 en un tv").

    Returns:
        Tupla ``(monto, None)`` o ``None`` si no hay número plausible.
    """
    match = re.search(r"\d[\d.,]*", text)
    if not match:
        return None
    num = _parse_decimal(match.group(0))
    if num is None or num < Decimal("0.01"):
        return None
    return num, None


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
    tipo: str = "pago",
) -> str:
    """Reduce el mensaje a un concepto: recorta verbos, cuentas y montos.

    Opera sobre el texto normalizado (sin acentos) para que el recorte
    sea consistente; se conserva el verbo principal cuando es parte del
    concepto ("comprar un televisor").
    """
    concept = _norm(message)

    for phrase in CONCEPT_STRIP:
        concept = re.sub(rf"\b{re.escape(phrase)}\b", " ", concept)

    for w in wallets:
        concept = re.sub(rf"\b{re.escape(_norm(w['name']))}\b", " ", concept)
        for token in _wallet_tokens(w["name"]):
            concept = re.sub(rf"\b{re.escape(token)}\b", " ", concept)

    if monto is not None:
        concept = re.sub(r"\d[\d.,]*", " ", concept)
        for unit in ("usd", "dólares", "dolares", "bs", "bolívares", "bolivares", "ves"):
            concept = re.sub(rf"\b{unit}\b", " ", concept)
        concept = concept.replace("$", " ").replace("€", " ")

    concept = _collapse(concept)
    while concept:
        lead = re.match(rf"\b(?:{'|'.join(re.escape(w) for w in CONCEPT_LEADING)})\b", concept)
        if not lead:
            break
        concept = _collapse(concept[lead.end():])
    while concept:
        trail = re.search(rf"\b(?:{'|'.join(re.escape(w) for w in CONCEPT_LEADING)})\b$", concept)
        if not trail:
            break
        concept = _collapse(concept[: trail.start()])
    concept = concept.strip(" .,;:·–-—")
    if not concept:
        # Sin contenido real: usa un concepto por defecto del tipo.
        return "Gasto registrado" if tipo == "pago" else "Ingreso registrado"
    return concept[:1].upper() + concept[1:]


def _collapse(text: str) -> str:
    """Colapsa espacios y signos repetidos."""
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s*([,;.:])\s*", r"\1 ", text)
    return text.strip()


def _has_any(text: str, patterns: list[str]) -> bool:
    return any(p in text for p in patterns)


def _has_reason(concepto: str) -> bool:
    """True si el concepto contiene una razón real (no solo restos de frase).

    "Navi", "acabo de" o "Gasto registrado" no son motivos; "Muebles" o
    "Comprar un televisor" sí. Se ignoran partículas y palabras residuales.
    """
    words = concepto.lower().replace(".", " ").split()
    significant = [
        w for w in words
        if w not in RESIDUAL_WORDS and w not in CONCEPT_LEADING
    ]
    return bool(significant)


#: Marcadores usados por ``_reason_phrase`` para aislar el motivo en
#: respuestas largas («El motivo del cobro es X y la moneda fue en…»).
#: Se prueban en orden (de más específico a más general).
_REASON_MARKERS = [
    "el motivo del cobro es", "el motivo del pago es",
    "el motivo del cobro fue", "el motivo del pago fue",
    "el motivo del cobro era", "el motivo del pago era",
    "la razon del cobro es", "la razon del pago es",
    "la razon del cobro fue", "la razon del pago fue",
    "el motivo es", "el motivo fue", "el motivo era",
    "la razon es", "la razon fue", "la razon era",
    "la causa es", "la causa fue", "fue por", "es por", "era por",
    "el motivo", "la razon",
]


def _reason_phrase(message: str) -> str | None:
    """Aísla la frase del motivo en una respuesta multi-dato.

    «El motivo del cobro es quincena y la moneda fue en bolívares por favor
    conviértelo» → «Quincena». Corta la cabecera tras el marcador y detiene
    la frase en la primera cláusula secundaria («y…», «por favor», etc.).

    Returns:
        Frase del motivo ya capitalizada, o ``None`` si el mensaje no trae
        marcador claro (se delega en el limpiador normal).
    """
    t = _norm(message)
    head: str | None = None
    for marker in _REASON_MARKERS:
        idx = t.find(marker)
        if idx != -1:
            head = t[idx + len(marker):].strip(" ,;:")
            break
    if head is None or not head:
        return None
    for stop in (
        " por favor", " y la moneda", " y el monto", " y la cuenta",
        " la moneda", " el monto", ",", ".", ";",
    ):
        idx = head.find(stop)
        if idx != -1:
            head = head[:idx]
            break
    idx = head.find(" y ")
    if idx != -1 and head[:idx].strip():
        head = head[:idx]
    head = head.strip(" ,;:")
    if not head:
        return None
    return head[:1].upper() + head[1:]


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
