"""tax_id — Normalización y validación de cédulas/RIF de clientes.

Una única fuente de verdad para el formato del documento fiscal de un
contacto: prefijo de tipo (V, J, E) y número. El valor canónico que se
guarda en ``BusinessContact.tax_id`` es ``<PREFIJO>-<NÚMERO>`` en
mayúsculas y sin espacios (ej. ``V-12345678``, ``J-310123456``).

Reglas por tipo:
- ``V`` venezolano: 6 a 8 dígitos.
- ``J`` jurídico (RIF de empresa): 9 a 11 dígitos.
- ``E`` extranjero: 5 a 12 caracteres alfanuméricos (pasaporte, etc.).
"""

from __future__ import annotations

import re

#: Prefijos válidos de cédula/RIF.
TAX_ID_TYPES = ("V", "J", "E")

#: Etiquetas legibles por tipo (para el admin y los mensajes).
TAX_ID_TYPE_LABELS = {"V": "Venezolano", "J": "Jurídico", "E": "Extranjero"}

#: Patrón del número según el tipo (anclado, sin la letra del prefijo).
TAX_ID_NUMBER_PATTERNS = {
    "V": re.compile(r"^\d{6,8}$"),
    "J": re.compile(r"^\d{9,11}$"),
    "E": re.compile(r"^[A-Z0-9]{5,12}$"),
}

#: Mensaje de ayuda cuando el número no cumple el formato de su tipo.
TAX_ID_FORMAT_HINTS = {
    "V": "La cédula de un venezolano es «V» seguida de 6 a 8 dígitos.",
    "J": "El RIF de una empresa es «J» seguido de 9 a 11 dígitos.",
    "E": "El documento de un extranjero es «E» seguido de 5 a 12 caracteres alfanuméricos.",
}

_SEPARATORS = re.compile(r"[\s.\-_]")


def split_tax_id(raw: str) -> tuple[str, str]:
    """Separa ``raw`` en ``(prefijo, número)`` ignorando espacios y guiones.

    Acepta entradas como ``" v-1234 "``, ``"V1234"`` o ``"1234"`` (sin
    prefijo). El prefijo queda en mayúsculas; ``""`` si no se reconoce.
    """
    text = _SEPARATORS.sub("", (raw or "").upper())
    if text[:1] in TAX_ID_TYPES:
        return text[0], text[1:]
    return "", text


def normalize_tax_id(raw: str) -> str:
    """Devuelve el documento en formato canónico ``PREFIJO-NÚMERO``.

    Si la entrada no trae prefijo se devuelve solo el número (así el
    llamador puede señalarlo como inválido). Cadena vacía si no hay nada
    que normalizar.
    """
    prefix, number = split_tax_id(raw)
    if not number:
        return ""
    if not prefix:
        return number
    return f"{prefix}-{number}"


def tax_id_error(raw: str) -> str | None:
    """Valida el documento y devuelve el mensaje de error, o ``None`` si es válido."""
    prefix, number = split_tax_id(raw)
    if not prefix:
        return "Indica el tipo de cédula (V, J o E) antes del número."
    if not number:
        return "Escribe el número de la cédula."
    if not TAX_ID_NUMBER_PATTERNS[prefix].match(number):
        return TAX_ID_FORMAT_HINTS[prefix]
    return None


def tax_id_search_term(term: str) -> str:
    """Normaliza el texto de búsqueda para que encuentre por cédula.

    Si el usuario escribe ``"v1234"`` se busca ``"V-1234"``; si escribe solo
    el número ``"1234"`` se deja limpio para que ``icontains`` encuentre
    ``V-1234`` dentro del valor almacenado.
    """
    prefix, number = split_tax_id(term)
    if prefix and number:
        return f"{prefix}-{number}"
    return number