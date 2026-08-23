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

#: Asunto enviado al agendar la eliminación de la cuenta.
SUBJECT_DELETE_SCHEDULED = "NaviCash — Tu cuenta se eliminará en 15 días"

#: Asunto enviado al cancelar una eliminación pendiente.
SUBJECT_DELETE_CANCELLED = "NaviCash — Eliminación de cuenta cancelada"

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


def send_account_deletion_email(email: str, name: str = "", grace_days: int | None = None) -> bool:
    """Confirma al usuario que su eliminación quedó agendada (período de gracia).

    Args:
        email: dirección del destinatario.
        name: nombre del usuario para el saludo.
        grace_days: días de gracia (default ``ACCOUNT_DELETION_GRACE_DAYS``).

    Returns:
        True si el envío fue aceptado.
    """
    days = grace_days or getattr(settings, "ACCOUNT_DELETION_GRACE_DAYS", 15)
    body = (
        f"Hola {name or ''},\n\n"
        "Recibimos tu solicitud para eliminar tu cuenta de NaviCash.\n\n"
        f"Por motivos legales y de seguridad, tus datos permanecerán en la "
        f"base de datos durante {days} días. Si cambias de opinión, puedes "
        "iniciar sesión en ese período y cancelar la eliminación desde tu "
        "perfil; pasado ese tiempo, tu cuenta y toda tu información se "
        "borrarán definitivamente y no podrán recuperarse.\n\n"
        "Si no solicitaste esto, te recomendamos cambiar tu contraseña de "
        "inmediato: alguien con acceso a tu cuenta pudo haberla pedido."
    )
    try:
        if _brevo_configured():
            _brevo_send(SUBJECT_DELETE_SCHEDULED, body, email)
        else:
            send_mail(
                SUBJECT_DELETE_SCHEDULED, body, settings.DEFAULT_FROM_EMAIL, [email],
                fail_silently=False,
            )
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("EMAIL_DELETE_SCHEDULED FAILED to=%s error=%r", email, exc)
        raise


def send_account_deletion_cancelled_email(email: str, name: str = "") -> bool:
    """Confirma que la eliminación pendiente fue cancelada a tiempo."""
    body = (
        f"Hola {name or ''},\n\n"
        "Tu eliminación de NaviCash fue cancelada: tu cuenta sigue activa "
        "con todos tus datos, como siempre.\n\n"
        "Si no fuiste tú quien canceló, cambia tu contraseña de inmediato."
    )
    try:
        if _brevo_configured():
            _brevo_send(SUBJECT_DELETE_CANCELLED, body, email)
        else:
            send_mail(
                SUBJECT_DELETE_CANCELLED, body, settings.DEFAULT_FROM_EMAIL, [email],
                fail_silently=False,
            )
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("EMAIL_DELETE_CANCELLED FAILED to=%s error=%r", email, exc)
        raise
