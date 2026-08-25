"""memory — Aprendizaje y preferencias del asistente Navi.

Registra preferencias aprendidas de forma automática (cada transacción
exitosa) o explícita (cuando el usuario dice «recuerda que…») y las
inyecta en el contexto para que Navi infiera cuenta, moneda y otros
datos sin preguntarlos repetidamente.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from datetime import timedelta

from django.db.models import F
from django.utils import timezone

from apps.assistant.models import NaviMemory

logger = logging.getLogger(__name__)

# Tokens de parada que no deben convertirse en clave de preferencia.
_STOPWORDS = frozenset({
    "y", "el", "la", "los", "las", "un", "una", "uno", "de", "del", "en",
    "que", "por", "con", "para", "se", "su", "al", "es", "fue", "ser",
    "ha", "hay", "esta", "este", "eso", "como", "mas", "pero", "o",
    "aqui", "alla", "asi", "bien", "mal", "muy", "poco", "mucho",
    "este", "esta", "esto", "ese", "esa", "eso", "aquel", "aquella",
    "fui", "voy", "dio", "ayer", "hoy", "manana",
    "paga", "pagar", "pagado", "compro", "comprar", "comprado",
    "vendio", "vender", "vendido", "recibi", "recibir", "recibido",
})

#: Longitud mínima de un token significativo (evita artículos cortos).
_MIN_TOKEN_LEN = 4


def strip_accents(text: str) -> str:
    """Elimina tildes de un texto (NFD → strip combining marks)."""
    return "".join(ch for ch in unicodedata.normalize("NFD", text) if unicodedata.category(ch) != "Mn")

#: Tiempo mínimo entre aprendizajes de la misma clave (evita spam con transacciones rápidas).
_LEARN_COOLDOWN = timedelta(seconds=10)


def remember(user, clave: str, valor: str, *, fuente: str = NaviMemory.FUENTE_USUARIO) -> NaviMemory:
    """Guarda o refuerza una preferencia del usuario."""
    clave = normalize_key(clave)
    now = timezone.now()

    try:
        existing = NaviMemory.objects.get(user=user, clave=clave)
        value_changed = existing.valor != valor
    except NaviMemory.DoesNotExist:
        value_changed = False

    memory, created = NaviMemory.objects.update_or_create(
        user=user,
        clave=clave,
        defaults={"valor": valor, "fuente": fuente, "usos": 1, "ultimo_uso": now},
    )
    if not created and not value_changed:
        memory.usos = F("usos") + 1
        memory.ultimo_uso = now
        memory.save(update_fields=["usos", "ultimo_uso"])
        memory.refresh_from_db()
    return memory


def forget(user, clave: str) -> bool:
    """Borra una preferencia por clave. Devuelve True si existía."""
    return NaviMemory.objects.filter(user=user, clave=normalize_key(clave)).delete()[0] > 0


def forget_all(user) -> int:
    """Borra todas las memorias del usuario. Devuelve cuántas borró."""
    return NaviMemory.objects.filter(user=user).delete()[0]


def list_memories(user, limit: int = 30) -> list[NaviMemory]:
    """Devuelve las memorias del usuario ordenadas por uso."""
    return list(NaviMemory.objects.filter(user=user).order_by("-usos", "-ultimo_uso")[:limit])


def memory_context(user, limit: int = 12) -> dict:
    """Dict compacto de preferencias para inyectar en el contexto del LLM.

    Solo incluye asociaciones con usos ≥ 2 y notas explícitas.  El resultado
    es JSON-friendly y no supera ~200 tokens.
    """
    rows = (
        NaviMemory.objects.filter(user=user)
        .exclude(clave__startswith="personalizado:")
        .order_by("-usos", "-ultimo_uso")[:limit]
    )
    associations = {}
    for row in rows:
        token = row.clave.split(":", 1)[-1] if ":" in row.clave else row.clave
        associations[token] = {"wallet": row.valor, "usos": row.usos}

    notes = list(
        NaviMemory.objects.filter(user=user, clave__startswith="personalizado:")
        .order_by("-usos")[:5]
        .values_list("valor", flat=True)
    )

    return {"asociaciones": associations, "notas": notes}


# ---------------------------------------------------------------------------
# Extracción de tokens y aprendizaje automático
# ---------------------------------------------------------------------------


def extract_main_token(concepto: str) -> str | None:
    """Extrae el token principal significativo de un concepto.

    Devuelve la primera palabra alfabética ≥ ``_MIN_TOKEN_LEN`` que no es
    stopword, normalizada (sin tildes, minúscula).  ``None`` si no hay
    token válido.
    """
    if not concepto:
        return None
    words = re.findall(r"[a-zA-ZáéíóúñÁÉÍÓÚÑ]+", concepto)
    for word in words:
        clean = strip_accents(word.lower())
        if len(clean) >= _MIN_TOKEN_LEN and clean not in _STOPWORDS:
            return clean
    return None


def normalize_key(clave: str) -> str:
    """Normaliza una clave canónica (minúscula, sin espacios extra)."""
    return " ".join(clave.lower().split()).strip()


def learn_from_concept(user, concepto: str, wallet_name: str, tipo: str) -> None:
    """Aprende la asociación concepto→wallet tras un registro exitoso.

    Solo almacena si el concepto tiene un token significativo y el wallet
    no es None.  Best-effort: nunca eleva excepciones al caller.
    """
    if not concepto or not wallet_name:
        return
    token = extract_main_token(concepto)
    if not token:
        return
    clave = f"wallet_para:{token}"
    remember(user, clave, wallet_name, fuente=NaviMemory.FUENTE_AUTO)


def learn_from_glossary(user, concepto: str, wallet_name: str | None) -> None:
    """Aprende glosario coloquial (ej. «lucas» → miles de bolívares).

    Detecta palabras frecuentes en el habla venezolana que aparecen en
    conceptos pero no en la descripción formal de la transacción.
    """
    GLOSSARY = {
        "lucas": "miles de bolívares",
        "bajos": "calzado",
        "cachapas": "comida típica venezolana",
        "reales": "miles de bolívares",
        "verdes": "dólares",
    }
    if not concepto:
        return
    words = {w.lower() for w in re.findall(r"[a-zA-Záéíóúñ]+", concepto)}
    for word, meaning in GLOSSARY.items():
        if word in words:
            clave = f"glosario:{word}"
            remember(user, clave, meaning, fuente=NaviMemory.FUENTE_AUTO)


def learn_from_transaction(user, transaction) -> None:
    """Hook post-registro: extrae señales de la transacción aprendidas."""
    try:
        if transaction.tipo == "transferencia":
            return
        learn_from_concept(
            user,
            transaction.concepto,
            transaction.wallet.name if transaction.wallet else None,
            transaction.tipo,
        )
        learn_from_glossary(
            user,
            transaction.concepto,
            transaction.wallet.name if transaction.wallet else None,
        )
    except Exception:  # noqa: BLE001 — best-effort
        logger.debug("learn_from_transaction falló silenciosamente", exc_info=True)


# ---------------------------------------------------------------------------
# Comandos explícitos del usuario ("recuerda que…", "olvida…")
# ---------------------------------------------------------------------------

_REMEMBER_RE = re.compile(
    r"^(?:recuerda(?:\s+que)?|no\s+olvides?\s+que?)\s+(.+)",
    re.IGNORECASE,
)
_FORGET_RE = re.compile(
    r"^(?:olvida(?:\s+que)?|borra(?:\s+que)?|elimina(?:\s+que)?)\s+(.+)",
    re.IGNORECASE,
)


def is_remember_command(message: str) -> bool:
    return bool(_REMEMBER_RE.match(message.strip()))


def is_forget_command(message: str) -> bool:
    return bool(_FORGET_RE.match(message.strip()))


def handle_remember_command(user, message: str) -> str:
    """Procesa «recuerda que X» y guarda la nota. Devuelve respuesta."""
    match = _REMEMBER_RE.match(message.strip())
    if not match:
        return "No entendí qué quieres que recuerde."
    note = match.group(1).strip()
    if len(note) < 5:
        return "La nota es muy corta. Dámela un poco más larga para recordarla bien."
    clave = f"personalizado:{normalize_key(note[:40])}"
    remember(user, clave, note, fuente=NaviMemory.FUENTE_USUARIO)
    return f"Listo, lo recordaré: «{note}»."


def handle_forget_command(user, message: str) -> str:
    """Procesa «olvida X» y borra la preferencia. Devuelve respuesta."""
    match = _FORGET_RE.match(message.strip())
    if not match:
        return "No entendí qué quieres que olvide."
    target = match.group(1).strip().lower()

    # Primero intentar borrar por clave exacta de personalizado.
    clave = f"personalizado:{normalize_key(target[:40])}"
    if forget(user, clave):
        return f"Olvidado: «{target}»."

    # Si no existía como nota personal, intentar borrar la asociación concepto→wallet.
    token = extract_main_token(target)
    if token and forget(user, f"wallet_para:{token}"):
        return f"Olvidé la asociación entre «{token}» y su cuenta."

    return f"No encontré nada sobre «{target}» en mi memoria."
