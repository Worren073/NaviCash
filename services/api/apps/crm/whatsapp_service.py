"""whatsapp_service — Integración con la WhatsApp Cloud API de Meta.

Agrupa la lógica pura de la integración (sin tocar la base de datos) para que
sea fácil de probar:

- ``verify_signature``: valida la firma HMAC ``X-Hub-Signature-256`` del webhook.
- ``extract_changes``: normaliza el payload anidado de Meta en una lista plana.
- ``describe_inbound``: resume un mensaje entrante (texto, tipo, vista previa).
- ``send_text``: envía un texto saliente por la Graph API.
"""

from __future__ import annotations

import hashlib
import hmac

import httpx
from django.conf import settings

# Códigos de la API de Meta que indican que no se puede responder con texto
# libre porque pasó la ventana de atención de 24 h (requiere plantilla).
_WINDOW_ERROR_CODES = {131047, 131026, 470}
_SIGNATURE_PREFIX = "sha256="


class WhatsAppSendError(Exception):
    """Error legible al enviar un mensaje por la API de Meta."""

    def __init__(self, message: str, code: str = "whatsapp_send_error") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


def verify_signature(app_secret: str, raw_body: bytes, signature_header: str) -> bool:
    """Comprueba la firma HMAC-SHA256 del cuerpo del webhook.

    Sin ``app_secret`` configurado devuelve True (modo desarrollo). Cuando sí
    está configurado, exige la cabecera ``X-Hub-Signature-256`` con el formato
    ``sha256=<hex>`` y compara en tiempo constante.
    """
    if not app_secret:
        return True
    if not signature_header or not signature_header.startswith(_SIGNATURE_PREFIX):
        return False
    provided = signature_header[len(_SIGNATURE_PREFIX):].strip()
    expected = hmac.new(app_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, provided)


def extract_changes(payload: dict) -> list[dict]:
    """Aplana el payload de Meta en ``{phone_number_id, field, value}``."""
    changes: list[dict] = []
    for entry in payload.get("entry", []) or []:
        for change in entry.get("changes", []) or []:
            value = change.get("value") or {}
            metadata = value.get("metadata") or {}
            changes.append(
                {
                    "phone_number_id": metadata.get("phone_number_id", ""),
                    "field": change.get("field", ""),
                    "value": value,
                }
            )
    return changes


def _first_message_text(message: dict) -> str:
    """Extrae el texto legible de un mensaje entrante (o un marcador)."""
    mtype = message.get("type", "unknown")
    if mtype == "text":
        return (message.get("text") or {}).get("body", "")
    if mtype == "button":
        return (message.get("button") or {}).get("text", "")
    if mtype == "interactive":
        interactive = message.get("interactive") or {}
        reply = interactive.get("button_reply") or interactive.get("list_reply") or {}
        return reply.get("title", "")
    labels = {
        "image": "[Imagen recibida]",
        "audio": "[Audio recibido]",
        "video": "[Video recibido]",
        "document": "[Documento recibido]",
        "sticker": "[Sticker recibido]",
        "location": "[Ubicación recibida]",
        "contacts": "[Contacto recibido]",
    }
    return labels.get(mtype, "[Mensaje no compatible]")


def describe_inbound(message: dict) -> dict:
    """Normaliza un mensaje entrante: id, tipo, texto y nombre del remitente."""
    return {
        "external_id": message.get("id", ""),
        "from": message.get("from", ""),
        "type": message.get("type", "text"),
        "body": _first_message_text(message),
    }


def send_text(phone_number_id: str, access_token: str, to: str, text: str) -> str:
    """Envía un texto por la Graph API; devuelve el ``wamid`` del mensaje.

    Lanza ``WhatsAppSendError`` con un mensaje en español ante cualquier fallo
    (credenciales, ventana de 24 h, red), para que la vista lo devuelva como
    400 sin exponer detalles internos.
    """
    if not access_token:
        raise WhatsAppSendError(
            "El número de WhatsApp no tiene un token de acceso configurado.",
            code="whatsapp_missing_token",
        )
    url = f"{settings.WHATSAPP_API_BASE_URL}/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"preview_url": False, "body": text},
    }
    try:
        response = httpx.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=15,
        )
    except httpx.HTTPError:
        raise WhatsAppSendError(
            "No se pudo contactar a WhatsApp. Revisa tu conexión e inténtalo de nuevo.",
            code="whatsapp_unreachable",
        )

    if response.status_code >= 400:
        raise _error_from_response(response)

    data = response.json()
    messages = data.get("messages") or []
    return messages[0].get("id", "") if messages else ""


def _error_from_response(response: httpx.Response) -> WhatsAppSendError:
    """Traduce el error de Meta a un mensaje en español orientado al usuario."""
    code = None
    try:
        error = (response.json() or {}).get("error", {}) or {}
        code = error.get("code")
        if code in _WINDOW_ERROR_CODES:
            return WhatsAppSendError(
                "No se pudo enviar: pasaron más de 24 horas desde el último "
                "mensaje del cliente. Envíale una plantilla para reiniciar la "
                "conversación.",
                code="whatsapp_window_closed",
            )
    except (ValueError, AttributeError):
        code = None

    if response.status_code in (401, 403):
        return WhatsAppSendError(
            "WhatsApp rechazó las credenciales. Verifica el token de acceso.",
            code="whatsapp_auth_error",
        )
    return WhatsAppSendError(
        "No se pudo enviar el mensaje por WhatsApp. Inténtalo de nuevo.",
        code="whatsapp_send_error",
    )
