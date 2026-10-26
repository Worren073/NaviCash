"""whatsapp_service – Integración con la WhatsApp Cloud API de Meta.

Agrupa la lógica pura de la integración (sin tocar la base de datos) para que
sea fácil de probar:

- ``verify_signature``: valida la firma HMAC ``X-Hub-Signature-256`` del webhook.
- ``extract_changes``: normaliza el payload anidado de Meta en una lista plana.
- ``describe_inbound``: resume un mensaje entrante (texto, tipo, vista previa).
- ``send_text``: envía un texto saliente por la Graph API.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
from typing import Any

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

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


def compute_appsecret_proof(access_token: str, app_secret: str | None = None) -> str | None:
    """Calcula el hash HMAC-SHA256 del access token con el app secret (requisito Graph API)."""
    secret = (app_secret or getattr(settings, "WHATSAPP_APP_SECRET", "") or "").strip()
    token = (access_token or "").strip()
    if not secret or not token:
        return None
    return hmac.new(secret.encode("utf-8"), token.encode("utf-8"), hashlib.sha256).hexdigest()


def send_text(
    phone_number_id: str,
    access_token: str,
    to: str,
    text: str,
    app_secret: str | None = None,
) -> str:
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
    params = {}
    proof = compute_appsecret_proof(access_token, app_secret)
    if proof:
        params["appsecret_proof"] = proof
    try:
        response = httpx.post(
            url,
            params=params,
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
                "mensaje del cliente. Envía una plantilla para reiniciar la "
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


def exchange_embedded_signup_code(app_id: str, app_secret: str, code: str, redirect_uri: str | None = None) -> dict[str, Any]:
    if not app_id or not app_secret or not code:
        raise WhatsAppSendError("Faltan datos para completar la vinculación con WhatsApp.", code="whatsapp_embedded_signup_missing")
    url = f"{settings.WHATSAPP_API_BASE_URL}/oauth/access_token"
    params = {"client_id": app_id, "client_secret": app_secret, "code": code}
    if redirect_uri:
        params["redirect_uri"] = redirect_uri
    try:
        response = httpx.get(url, params=params, timeout=15)
    except httpx.HTTPError:
        raise WhatsAppSendError("No se pudo contactar a Meta. Inténtalo de nuevo.", code="whatsapp_embedded_signup_unreachable")
    if response.status_code >= 400:
        raise _error_from_response(response)
    return response.json() or {}


def get_waba_accounts(user_access_token: str) -> list[dict[str, Any]]:
    if not user_access_token:
        raise WhatsAppSendError("Token de acceso inválido para Embedded Signup.", code="whatsapp_embedded_signup_missing")
    url = f"{settings.WHATSAPP_API_BASE_URL}/me/whatsapp_business_accounts"
    try:
        response = httpx.get(url, params={"access_token": user_access_token, "fields": "id,name"}, timeout=15)
    except httpx.HTTPError:
        raise WhatsAppSendError("No se pudo obtener las cuentas de WhatsApp Business.", code="whatsapp_embedded_signup_unreachable")
    if response.status_code >= 400:
        raise _error_from_response(response)
    data = response.json() or {}
    return data.get("data") or []


def get_phone_numbers(waba_id: str, access_token: str) -> list[dict[str, Any]]:
    if not waba_id or not access_token:
        raise WhatsAppSendError("Faltan datos para obtener el número de teléfono.", code="whatsapp_embedded_signup_missing")
    url = f"{settings.WHATSAPP_API_BASE_URL}/{waba_id}/phone_numbers"
    try:
        response = httpx.get(url, params={"access_token": access_token, "fields": "id,display_phone_number,verified_name,code_verification_status"}, timeout=15)
    except httpx.HTTPError:
        raise WhatsAppSendError("No se pudo obtener los números de teléfono.", code="whatsapp_embedded_signup_unreachable")
    if response.status_code >= 400:
        raise _error_from_response(response)
    data = response.json() or {}
    return data.get("data") or []


def subscribe_app_to_waba(waba_id: str, access_token: str, app_secret: str | None = None) -> bool:
    """Suscribe la app de Meta a los eventos de la WABA del negocio (requisito para recibir webhooks).

    POST /{waba_id}/subscribed_apps
    """
    if not waba_id or not access_token:
        raise WhatsAppSendError(
            "Faltan datos para suscribir la app a la cuenta de WhatsApp Business (WABA).",
            code="whatsapp_missing_waba_data",
        )
    url = f"{settings.WHATSAPP_API_BASE_URL}/{waba_id}/subscribed_apps"
    params = {}
    proof = compute_appsecret_proof(access_token, app_secret)
    if proof:
        params["appsecret_proof"] = proof
    try:
        response = httpx.post(
            url,
            params=params,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=15,
        )
    except httpx.HTTPError:
        raise WhatsAppSendError(
            "No se pudo contactar a Meta para suscribir la aplicación al WABA.",
            code="whatsapp_unreachable",
        )
    if response.status_code >= 400:
        raise _error_from_response(response)
    data = response.json() or {}
    return bool(data.get("success", False))


def unsubscribe_app_from_waba(waba_id: str, access_token: str, app_secret: str | None = None) -> bool:
    """Desuscribe la app de la WABA al desconectar WhatsApp (best-effort).

    DELETE /{waba_id}/subscribed_apps
    """
    if not waba_id or not access_token:
        return False
    url = f"{settings.WHATSAPP_API_BASE_URL}/{waba_id}/subscribed_apps"
    params = {}
    proof = compute_appsecret_proof(access_token, app_secret)
    if proof:
        params["appsecret_proof"] = proof
    try:
        response = httpx.delete(
            url,
            params=params,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=15,
        )
        return response.status_code < 400 and (response.json() or {}).get("success", False)
    except Exception as exc:
        logger.warning("Fallo al desuscribir WABA %s: %s", waba_id, exc)
        return False


def revoke_meta_token(access_token: str, app_secret: str | None = None) -> bool:
    """Revoca los permisos del token de acceso en Meta al desconectar (best-effort).

    DELETE /me/permissions
    """
    if not access_token:
        return False
    url = f"{settings.WHATSAPP_API_BASE_URL}/me/permissions"
    params = {}
    proof = compute_appsecret_proof(access_token, app_secret)
    if proof:
        params["appsecret_proof"] = proof
    try:
        response = httpx.delete(
            url,
            params=params,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=15,
        )
        return response.status_code < 400 and (response.json() or {}).get("success", False)
    except Exception as exc:
        logger.warning("Fallo al revocar token de Meta: %s", exc)
        return False


def inspect_token(input_token: str, app_id: str | None = None, app_secret: str | None = None) -> dict[str, Any]:
    """Valida y consulta el ciclo de vida de un token vía /debug_token de Graph API."""
    app_id = (app_id or getattr(settings, "WHATSAPP_APP_ID", "") or "").strip()
    app_secret = (app_secret or getattr(settings, "WHATSAPP_APP_SECRET", "") or "").strip()
    token = (input_token or "").strip()
    if not app_id or not app_secret or not token:
        return {
            "is_valid": False,
            "error": "Faltan credenciales de aplicación o token para depurar.",
        }

    url = f"{settings.WHATSAPP_API_BASE_URL}/debug_token"
    params = {
        "input_token": token,
        "access_token": f"{app_id}|{app_secret}",
    }
    try:
        response = httpx.get(url, params=params, timeout=15)
    except httpx.HTTPError:
        return {
            "is_valid": False,
            "error": "No se pudo contactar a Meta para verificar el token.",
        }

    if response.status_code >= 400:
        return {
            "is_valid": False,
            "error": "Meta rechazó la consulta de depuración de token.",
        }

    data = (response.json() or {}).get("data") or {}
    return {
        "is_valid": bool(data.get("is_valid", False)),
        "expires_at": data.get("expires_at"),
        "scopes": data.get("scopes", []),
        "type": data.get("type", "USER"),
        "user_id": data.get("user_id"),
        "app_id": data.get("app_id"),
        "raw": data,
    }


def get_phone_number_details(phone_number_id: str, access_token: str, app_secret: str | None = None) -> dict[str, Any]:
    """Obtiene metadatos actualizados del número (nombre verificado, calidad, tier)."""
    if not phone_number_id or not access_token:
        return {}
    url = f"{settings.WHATSAPP_API_BASE_URL}/{phone_number_id}"
    params = {
        "fields": "verified_name,quality_rating,code_verification_status,messaging_limit_tier,display_phone_number",
    }
    proof = compute_appsecret_proof(access_token, app_secret)
    if proof:
        params["appsecret_proof"] = proof
    try:
        response = httpx.get(
            url,
            params=params,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=15,
        )
        if response.status_code < 400:
            return response.json() or {}
    except Exception as exc:
        logger.warning("Fallo al consultar número %s de Meta: %s", phone_number_id, exc)
    return {}


def parse_signed_request(signed_request: str, app_secret: str) -> dict[str, Any] | None:
    """Parsea y valida la firma HMAC-SHA256 de un signed_request de Meta (GDPR Data Deletion Callback).

    Formato: <encoded_sig>.<payload>
    """
    if not signed_request or "." not in signed_request or not app_secret:
        return None
    try:
        encoded_sig, payload = signed_request.split(".", 1)
        sig_padding = "=" * ((4 - len(encoded_sig) % 4) % 4)
        data_padding = "=" * ((4 - len(payload) % 4) % 4)
        sig_bytes = base64.urlsafe_b64decode(encoded_sig + sig_padding)
        data_bytes = base64.urlsafe_b64decode(payload + data_padding)

        expected_sig = hmac.new(app_secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).digest()
        if not hmac.compare_digest(sig_bytes, expected_sig):
            return None
        return json.loads(data_bytes.decode("utf-8"))
    except Exception as exc:
        logger.warning("Fallo al parsear signed_request: %s", exc)
        return None


def sanitize_log_data(data: Any) -> Any:
    """Enmascara datos sensibles (tokens, secretos, contraseñas) para registros de auditoría y logs."""
    if isinstance(data, dict):
        sanitized = {}
        for k, v in data.items():
            key_lower = str(k).lower()
            if any(term in key_lower for term in ("token", "secret", "password", "authorization", "code")):
                sanitized[k] = "***REDACTED***"
            else:
                sanitized[k] = sanitize_log_data(v)
        return sanitized
    if isinstance(data, list):
        return [sanitize_log_data(item) for item in data]
    return data

