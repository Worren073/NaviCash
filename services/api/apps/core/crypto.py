"""crypto — Cifrado simétrico de secretos en reposo (Fernet / MultiFernet).

Se usa para guardar credenciales de terceros (p. ej. tokens de la API de
WhatsApp) que deben poder recuperarse en claro para usarlas contra el
proveedor, pero nunca quedar legibles si la base de datos se filtra.

La clave viene de ``FIELD_ENCRYPTION_KEY`` (una clave Fernet en base64 urlsafe,
o múltiples claves separadas por coma para permitir rotación sin tiempo de baja).
En producción (DEBUG=False) la clave es obligatoria (fail-fast). En desarrollo
o tests sin clave se deriva de ``DJANGO_SECRET_KEY``.
"""

from __future__ import annotations

import base64
import hashlib
import sys

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings


def _is_test_environment() -> bool:
    """Detecta si el proceso está corriendo bajo tests unitarios."""
    if getattr(settings, "TESTING", False):
        return True
    return "pytest" in sys.modules or (len(sys.argv) > 0 and "pytest" in sys.argv[0])


def _fernet() -> Fernet | MultiFernet:
    """Construye el cifrador Fernet o MultiFernet para rotación segura."""
    raw_key = getattr(settings, "FIELD_ENCRYPTION_KEY", "") or ""
    keys = [k.strip() for k in str(raw_key).split(",") if k.strip()]

    if not keys:
        if not getattr(settings, "DEBUG", True) and not _is_test_environment():
            raise RuntimeError(
                "FIELD_ENCRYPTION_KEY es obligatoria en producción (DEBUG=False). "
                "Define una clave Fernet válida para proteger secretos en reposo."
            )
        digest = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
        return Fernet(base64.urlsafe_b64encode(digest))

    fernets = [Fernet(k.encode("ascii") if isinstance(k, str) else k) for k in keys]
    return MultiFernet(fernets) if len(fernets) > 1 else fernets[0]


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
