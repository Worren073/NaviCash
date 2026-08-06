"""captcha — Verificación del CAPTCHA de Cloudflare Turnstile.

En desarrollo (sin ``TURNSTILE_SECRET_KEY`` y con ``CAPTCHA_DEV_BYPASS=True``)
la verificación se omite para no bloquear el flujo local; en producción se
valida el token obtenido por el widget en el frontend contra la API de Turnstile.
"""

from __future__ import annotations

import httpx
from django.conf import settings


def captcha_enabled() -> bool:
    """True si hay que verificar el CAPTCHA (clave configurada o bypass off)."""
    return bool(settings.TURNSTILE_SECRET_KEY) or not settings.CAPTCHA_DEV_BYPASS


def verify_turnstile(token: str) -> bool:
    """Verifica un token de Turnstile contra la API de Cloudflare.

    Args:
        token: respuesta del widget Turnstile (o string vacío).

    Returns:
        True si el token es válido o si el CAPTCHA no está activo en dev.
    """
    if not captcha_enabled():
        return True
    if not settings.TURNSTILE_SECRET_KEY or not token:
        return False
    try:
        resp = httpx.post(
            settings.TURNSTILE_VERIFY_URL,
            data={
                "secret": settings.TURNSTILE_SECRET_KEY,
                "response": token,
            },
            timeout=5.0,
        )
        resp.raise_for_status()
        return bool(resp.json().get("success"))
    except (httpx.HTTPError, ValueError):
        return False