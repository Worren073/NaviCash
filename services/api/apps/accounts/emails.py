"""emails — Envío de correos de NaviCash (verificación y recuperación).

En desarrollo/tests se usa el backend de Django de consola (los correos se
imprimen en los logs / se inspeccionan con ``django.core.mail.outbox``). En
producción el envío sale por la API HTTP de Brevo (puerto 443), ya que el
egress SMTP (puertos 465/587) está bloqueado por red en el proveedor.
"""

from __future__ import annotations

import logging
from urllib.parse import quote

import httpx
from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)

#: Asunto enviado al registrar un usuario (verificación de email).
SUBJECT_VERIFY = "NaviCash — Confirma tu correo"

#: Asunto enviado al solicitar recuperación de contraseña.
SUBJECT_RESET = "NaviCash — Restablece tu contraseña"

#: Endpoint de la API HTTP de Brevo.
BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"


def _brevo_configured() -> bool:
    """True si el envío debe salir por la API HTTP de Brevo.

    Solo en producción (no DEBUG/TEST) y con ``BREVO_API_KEY`` presente.
    En desarrollo/tests se mantiene el backend de consola para no romper los
    tests que inspeccionan ``django.core.mail.outbox``.
    """
    if settings.DEBUG or getattr(settings, "TEST", False):
        return False
    return bool(getattr(settings, "BREVO_API_KEY", ""))


def _brevo_send(subject: str, body: str, to_email: str) -> bool:
    """Envía un correo por la API HTTP de Brevo (puerto 443).

    Raises:
        httpx.HTTPError: si la API de Brevo no responde o devuelve error.
    """
    resp = httpx.post(
        BREVO_API_URL,
        headers={
            "api-key": settings.BREVO_API_KEY,
            "accept": "application/json",
            "content-type": "application/json",
        },
        json={
            "sender": {
                "name": settings.BREVO_SENDER_NAME,
                "email": settings.BREVO_SENDER_EMAIL,
            },
            "to": [{"email": to_email}],
            "subject": subject,
            "textContent": body,
        },
        timeout=10.0,
    )
    resp.raise_for_status()
    return True


def send_verification_email(email: str, token: str, name: str = "") -> bool:
    """Envía el correo de confirmación de email con su token.

    Args:
        email: dirección del destinatario.
        token: token de verificación (caduca en VERIFICATION_TOKEN_HOURS h).
        name: nombre del usuario para personalizar el saludo.

    Returns:
        True si el envío fue aceptado (Brevo en prod, consola en dev/tests).
    """
    # En desarrollo el frontend usa este endpoint para volver el token a la app.
    url = f"{settings.APP_BASE_URL}/verify?token={token}"
    body = (
        f"Hola {name or '¡Hola!'},\n\n"
        f"Para activar tu cuenta de NaviCash haz clic en el siguiente enlace:\n{url}\n\n"
        f"El enlace caduca en {getattr(settings, 'VERIFICATION_TOKEN_HOURS', 24)} horas.\n\n"
        "Si no solicitaste esta cuenta, ignora este correo."
    )
    logger.info(
        "EMAIL_VERIFY to=%s from=%s via=%s",
        email,
        settings.BREVO_SENDER_EMAIL if _brevo_configured() else settings.DEFAULT_FROM_EMAIL,
        "brevo-http" if _brevo_configured() else settings.EMAIL_BACKEND,
    )
    try:
        if _brevo_configured():
            _brevo_send(SUBJECT_VERIFY, body, email)
        else:
            send_mail(SUBJECT_VERIFY, body, settings.DEFAULT_FROM_EMAIL, [email], fail_silently=False)
        logger.info("EMAIL_VERIFY sent ok to=%s", email)
        return True
    except Exception as exc:  # noqa: BLE001 - loguear cualquier fallo del envío
        logger.error("EMAIL_VERIFY FAILED to=%s error=%r", email, exc)
        raise


def send_password_reset_email(email: str, token: str) -> bool:
    """Envía el correo para restablecer la contraseña.

    Args:
        email: dirección del destinatario.
        token: token plano de recuperación (one-time, caduca en ~30 min).

    Returns:
        True si el envío fue aceptado.
    """
    url = f"{settings.APP_BASE_URL}/reset-password?token={token}&email={quote(email)}"
    body = (
        "Recibimos una solicitud para restablecer tu contraseña de NaviCash.\n\n"
        f"Usa este enlace (caduca en 30 minutos):\n{url}\n\n"
        "Si no la solicitaste, ignora este correo."
    )
    try:
        if _brevo_configured():
            _brevo_send(SUBJECT_RESET, body, email)
        else:
            send_mail(SUBJECT_RESET, body, settings.DEFAULT_FROM_EMAIL, [email], fail_silently=False)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("EMAIL_RESET FAILED to=%s error=%r", email, exc)
        raise
