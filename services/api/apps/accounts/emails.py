"""emails — Envío de correos de NaviCash (verificación y recuperación).

En desarrollo se usa el backend de Django de consola (los correos se imprimen
en los logs del contenedor). En producción se configura un SMTP
(Resend/Brevo/SendGrid) vía variables de entorno (DJANGO_EMAIL_*).
"""

from __future__ import annotations

from django.conf import settings
from django.core.mail import send_mail

#: Asunto enviado al registrar un usuario (verificación de email).
SUBJECT_VERIFY = "NaviCash — Confirma tu correo"

#: Asunto enviado al solicitar recuperación de contraseña.
SUBJECT_RESET = "NaviCash — Restablece tu contraseña"


def send_verification_email(email: str, token: str, name: str = "") -> bool:
    """Envía el correo de confirmación de email con su token.

    Args:
        email: dirección del destinatario.
        token: token de verificación (caduca en VERIFICATION_TOKEN_HOURS h).
        name: nombre del usuario para personalizar el saludo.

    Returns:
        True si `send_mail` aceptó el envío (siempre en consola).
    """
    # En desarrollo el frontend usa este endpoint para volver el token a la app.
    url = f"{settings.APP_BASE_URL}/verificar?token={token}"
    body = (
        f"Hola {name or '¡Hola!'},\n\n"
        f"Para activar tu cuenta de NaviCash haz clic en el siguiente enlace:\n{url}\n\n"
        f"El enlace caduca en {getattr(settings, 'VERIFICATION_TOKEN_HOURS', 24)} horas.\n\n"
        "Si no solicitaste esta cuenta, ignora este correo."
    )
    return send_mail(SUBJECT_VERIFY, body, settings.DEFAULT_FROM_EMAIL, [email], fail_silently=False)


def send_password_reset_email(email: str, token: str) -> bool:
    """Envía el correo para restablecer la contraseña.

    Args:
        email: dirección del destinatario.
        token: token de reseteo de contraseña.

    Returns:
        True si el envío fue aceptado.
    """
    url = f"{settings.APP_BASE_URL}/recuperar?token={token}"
    body = (
        "Recibimos una solicitud para restablecer tu contraseña de NaviCash.\n\n"
        f"Usa este enlace:\n{url}\n\n"
        "Si no la solicitaste, ignora este correo."
    )
    return send_mail(SUBJECT_RESET, body, settings.DEFAULT_FROM_EMAIL, [email], fail_silently=False)