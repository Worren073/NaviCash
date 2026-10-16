"""crypto — Cifrado simétrico de secretos en reposo (Fernet).

Se usa para guardar credenciales de terceros (p. ej. tokens de la API de
WhatsApp) que deben poder recuperarse en claro para usarlas contra el
proveedor, pero nunca quedar legibles si la base de datos se filtra.

La clave viene de ``FIELD_ENCRYPTION_KEY`` (una clave Fernet en base64 urlsafe).
Si no está configurada se deriva de ``DJANGO_SECRET_KEY``: es seguro (el
secreto no es público) y evita romper el despliegue, aunque se recomienda
definir ``FIELD_ENCRYPTION_KEY`` explícita para poder rotar ``SECRET_KEY`` sin
invalidar los secretos ya cifrados.
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _fernet() -> Fernet:
    """Construye el cifrador con la clave configurada o derivada del SECRET_KEY."""
    key = getattr(settings, "FIELD_ENCRYPTION_KEY", "") or ""
    if not key:
        digest = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
        key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_value(raw: str | None) -> str:
    """Cifra un texto en claro; devuelve "" si la entrada está vacía."""
    if not raw:
        return ""
    return _fernet().encrypt(raw.encode("utf-8")).decode("ascii")


def decrypt_value(token: str | None) -> str:
    """Descifra un token; devuelve "" si está vacío o no es descifrable.

    Un token ilegible (clave rotada o dato corrupto) no debe reventar la
    petición: se trata como "sin credencial" y la operación fallará de forma
    controlada más adelante.
    """
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        return ""
