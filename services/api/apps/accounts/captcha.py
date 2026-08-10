"""captcha — Verificación del CAPTCHA de Cloudflare Turnstile.

En desarrollo (``DEBUG=True`` o ``settings.TEST``) la verificación se omite
(bypass) para no bloquear el flujo local. En producción la verificación es
FAIL-CLOSED (AUDIT A1): si falta ``TURNSTILE_SECRET_KEY`` o el token del
widget no es válido contra la API de Turnstile, se rechaza la petición —
nunca se abre silenciosamente.
"""

from __future__ import annotations

import httpx
from django.conf import settings


def captcha_enabled() -> bool:
    """True si hay que verificar el CAPTCHA en este entorno.

    El bypass solo aplica en desarrollo/tests (``DEBUG`` o ``settings.TEST``):
    en producción el interruptor global ``CAPTCHA_ENABLED`` (True por defecto)
    controla la verificación, que siempre es fail-closed.
    """
    if settings.DEBUG or getattr(settings, "TEST", False):
        return False
    return bool(getattr(settings, "CAPTCHA_ENABLED", True))


def verify_turnstile(token: str) -> bool:
    """Verifica un token de Turnstile contra la API de Cloudflare.

    Args:
        token: respuesta del widget Turnstile (o string vacío).

    Returns:
        True solo si el CAPTCHA no está activo (dev/test) o si el token fue
        validado contra Cloudflare. En producción, sin clave o con token
        inválido/ausente devuelve False (fail-closed).
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