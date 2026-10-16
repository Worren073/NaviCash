"""instagram_service — Integración con la mensajería de Instagram (Instagram Login).

Agrupa la lógica de la integración sin tocar la base de datos:

- OAuth: ``build_authorize_url`` / ``exchange_code`` / ``exchange_long_lived`` /
  ``refresh_long_lived`` (Instagram Login: token de usuario, sin Página de FB).
- Perfil: ``fetch_profile`` (usuario, nombre y foto).
- Webhook: ``verify_signature`` (reutilizado de WhatsApp) + ``extract_events`` /
  ``describe_inbound`` / ``extract_attachments``.
- Envío: ``send_text`` / ``send_attachment`` por la Graph API de Instagram.

La firma del webhook es idéntica a la de Meta (HMAC-SHA256 sobre el cuerpo), por
eso se reutiliza ``verify_signature`` de ``whatsapp_service``.
"""

from __future__ import annotations

from urllib.parse import urlencode

import httpx
from django.conf import settings

from apps.crm.whatsapp_service import verify_signature  # noqa: F401 (re-export)

# Base del OAuth de Instagram Login (independiente de la Graph API de mensajería).
_AUTHORIZE_URL = "https://www.instagram.com/oauth/authorize"
_TOKEN_URL = "https://api.instagram.com/oauth/access_token"
_LONG_LIVED_URL = "https://graph.instagram.com/access_token"
_REFRESH_URL = "https://graph.instagram.com/refresh_access_token"

# Permisos mínimos para leer el perfil y gestionar la mensajería.
OAUTH_SCOPES = "instagram_business_basic,instagram_business_manage_messages"

# Tipos de adjunto que Instagram acepta como saliente.
_SENDABLE_ATTACHMENTS = {"image", "video", "audio", "file"}

# Subcódigos del error code 10 que indican que pasó la ventana de 24 h.
_WINDOW_SUBCODES = {2018278, 2534022}

_PLACEHOLDERS = {
    "image": "[Imagen recibida]",
    "video": "[Video recibido]",
    "audio": "[Audio recibido]",
    "file": "[Archivo recibido]",
    "share": "[Publicación compartida]",
    "story_mention": "[Mención en historia]",
    "ig_reel": "[Reel compartido]",
    "sticker": "[Sticker recibido]",
    "link": "[Enlace recibido]",
}


class InstagramError(Exception):
    """Error legible de la integración con Instagram."""

    def __init__(self, message: str, code: str = "instagram_error") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class InstagramSendError(InstagramError):
    """Error legible al enviar un mensaje por la API de Instagram."""


# ---------------------------------------------------------------------------
# OAuth (Instagram Login)
# ---------------------------------------------------------------------------


def build_authorize_url(state: str) -> str:
    """URL de autorización a la que redirigir al negocio para conectar su cuenta."""
    params = {
        "client_id": settings.INSTAGRAM_APP_ID,
        "redirect_uri": settings.INSTAGRAM_REDIRECT_URI,
        "response_type": "code",
        "scope": OAUTH_SCOPES,
        "enable_fb_login": "0",
        "state": state,
    }
    return f"{_AUTHORIZE_URL}?{urlencode(params)}"


def exchange_code(code: str) -> dict:
    """Canjea el ``code`` por un token de corta vida (1 h) y el ``user_id``."""
    data = {
        "client_id": settings.INSTAGRAM_APP_ID,
        "client_secret": settings.INSTAGRAM_APP_SECRET,
        "grant_type": "authorization_code",
        "redirect_uri": settings.INSTAGRAM_REDIRECT_URI,
        "code": code,
    }
    payload = _post_form(_TOKEN_URL, data, code="instagram_oauth_error")
    return {
        "access_token": payload.get("access_token", ""),
        "user_id": str(payload.get("user_id", "")),
        "permissions": payload.get("permissions", []),
    }


def exchange_long_lived(short_token: str) -> dict:
    """Cambia un token de corta vida por uno de larga duración (~60 días)."""
    params = {
        "grant_type": "ig_exchange_token",
        "client_secret": settings.INSTAGRAM_APP_SECRET,
        "access_token": short_token,
    }
    payload = _get_json(_LONG_LIVED_URL, params, code="instagram_oauth_error")
    return {
        "access_token": payload.get("access_token", ""),
        "expires_in": int(payload.get("expires_in", 0) or 0),
    }


def refresh_long_lived(long_token: str) -> dict:
    """Refresca un token de larga duración antes de que caduque."""
    params = {"grant_type": "ig_refresh_token", "access_token": long_token}
    payload = _get_json(_REFRESH_URL, params, code="instagram_oauth_error")
    return {
        "access_token": payload.get("access_token", ""),
        "expires_in": int(payload.get("expires_in", 0) or 0),
    }


def fetch_profile(ig_user_id: str, access_token: str) -> dict:
    """Obtiene usuario, nombre y foto de perfil de la cuenta conectada."""
    url = f"{settings.INSTAGRAM_API_BASE_URL}/{ig_user_id}"
    params = {"fields": "id,username,name,profile_picture_url", "access_token": access_token}
    try:
        response = httpx.get(url, params=params, timeout=15)
    except httpx.HTTPError:
        return {}
    if response.status_code >= 400:
        return {}
    try:
        data = response.json() or {}
    except ValueError:
        return {}
    return {
        "username": data.get("username", ""),
        "name": data.get("name", ""),
        "profile_picture_url": data.get("profile_picture_url", ""),
    }


# ---------------------------------------------------------------------------
# Webhook: parseo de eventos entrantes
# ---------------------------------------------------------------------------


def extract_events(payload: dict) -> list[dict]:
    """Aplana el payload de Instagram en una lista de eventos de mensajería.

    Instagram entrega los eventos en ``entry[].messaging[]`` (a diferencia de
    WhatsApp, que usa ``entry[].changes[]``). ``entry.id`` es el IG ID de la
    cuenta profesional: con él se localiza al negocio destinatario.
    """
    events: list[dict] = []
    for entry in payload.get("entry", []) or []:
        ig_user_id = str(entry.get("id", ""))
        for messaging in entry.get("messaging", []) or []:
            message = messaging.get("message") or {}
            sender = (messaging.get("sender") or {}).get("id", "")
            recipient = (messaging.get("recipient") or {}).get("id", "")
            events.append(
                {
                    "ig_user_id": ig_user_id,
                    "sender_id": str(sender),
                    "recipient_id": str(recipient),
                    "message": message,
                    "mid": str(message.get("mid", "")),
                    "is_echo": bool(message.get("is_echo")),
                    "timestamp": messaging.get("timestamp"),
                }
            )
    return events


def extract_attachments(message: dict) -> list[dict]:
    """Normaliza los adjuntos de un mensaje: ``{kind, url}`` por cada uno."""
    attachments: list[dict] = []
    for item in message.get("attachments", []) or []:
        payload = item.get("payload") or {}
        url = payload.get("url", "")
        if not url:
            continue
        attachments.append({"kind": item.get("type", "unknown"), "url": url})
    return attachments


def describe_inbound(event: dict) -> dict:
    """Normaliza un evento entrante: id, remitente, tipo, texto y adjuntos."""
    message = event.get("message") or {}
    attachments = extract_attachments(message)
    text = message.get("text", "")
    if text:
        message_type = "text"
        body = text
    else:
        message_type = attachments[0]["kind"] if attachments else "unknown"
        body = _PLACEHOLDERS.get(message_type, "[Mensaje no compatible]")
    return {
        "external_id": event.get("mid", ""),
        "from": event.get("sender_id", ""),
        "type": message_type,
        "body": body,
        "attachments": attachments,
        "is_echo": bool(event.get("is_echo")),
    }


# ---------------------------------------------------------------------------
# Envío saliente
# ---------------------------------------------------------------------------


def send_text(ig_user_id: str, access_token: str, to: str, text: str) -> str:
    """Envía un texto por la API de Instagram; devuelve el ``mid`` del mensaje."""
    payload = {"recipient": {"id": to}, "message": {"text": text}}
    return _send(ig_user_id, access_token, to, payload)


def send_attachment(
    ig_user_id: str, access_token: str, to: str, kind: str, url: str
) -> str:
    """Envía un adjunto (por URL pública) por la API de Instagram."""
    if kind not in _SENDABLE_ATTACHMENTS:
        kind = "file"
    payload = {
        "recipient": {"id": to},
        "message": {"attachment": {"type": kind, "payload": {"url": url}}},
    }
    return _send(ig_user_id, access_token, to, payload)


def _send(ig_user_id: str, access_token: str, to: str, payload: dict) -> str:
    if not access_token:
        raise InstagramSendError(
            "La cuenta de Instagram no tiene un token de acceso configurado.",
            code="instagram_missing_token",
        )
    url = f"{settings.INSTAGRAM_API_BASE_URL}/{ig_user_id}/messages"
    try:
        response = httpx.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=15,
        )
    except httpx.HTTPError:
        raise InstagramSendError(
            "No se pudo contactar a Instagram. Revisa tu conexión e inténtalo de nuevo.",
            code="instagram_unreachable",
        )
    if response.status_code >= 400:
        raise _error_from_response(response)
    try:
        data = response.json() or {}
    except ValueError:
        return ""
    return str(data.get("message_id") or data.get("id") or "")


def _error_from_response(response: httpx.Response) -> InstagramSendError:
    """Traduce el error de Meta a un mensaje en español orientado al usuario."""
    code = None
    subcode = None
    try:
        error = (response.json() or {}).get("error", {}) or {}
        code = error.get("code")
        subcode = error.get("error_subcode")
    except (ValueError, AttributeError):
        code = None
    if code == 10 and subcode in _WINDOW_SUBCODES:
        return InstagramSendError(
            "No se pudo enviar: pasaron más de 24 horas desde el último mensaje "
            "del cliente. Espera a que vuelva a escribir para responder.",
            code="instagram_window_closed",
        )
    if response.status_code in (401, 403):
        return InstagramSendError(
            "Instagram rechazó las credenciales. Vuelve a conectar la cuenta.",
            code="instagram_auth_error",
        )
    return InstagramSendError(
        "No se pudo enviar el mensaje por Instagram. Inténtalo de nuevo.",
        code="instagram_send_error",
    )


# ---------------------------------------------------------------------------
# Helpers HTTP
# ---------------------------------------------------------------------------


def _post_form(url: str, data: dict, *, code: str) -> dict:
    try:
        response = httpx.post(url, data=data, timeout=15)
    except httpx.HTTPError:
        raise InstagramError(
            "No se pudo contactar a Instagram. Revisa tu conexión e inténtalo de nuevo.",
            code="instagram_unreachable",
        )
    if response.status_code >= 400:
        raise _oauth_error_from_response(response, code)
    try:
        return response.json() or {}
    except ValueError:
        raise InstagramError("Respuesta no válida de Instagram.", code=code)


def _get_json(url: str, params: dict, *, code: str) -> dict:
    try:
        response = httpx.get(url, params=params, timeout=15)
    except httpx.HTTPError:
        raise InstagramError(
            "No se pudo contactar a Instagram. Revisa tu conexión e inténtalo de nuevo.",
            code="instagram_unreachable",
        )
    if response.status_code >= 400:
        raise _oauth_error_from_response(response, code)
    try:
        return response.json() or {}
    except ValueError:
        raise InstagramError("Respuesta no válida de Instagram.", code=code)


def _oauth_error_from_response(response: httpx.Response, code: str) -> InstagramError:
    return InstagramError(
        "No se pudo completar la conexión con Instagram. Inténtalo de nuevo.",
        code=code,
    )
