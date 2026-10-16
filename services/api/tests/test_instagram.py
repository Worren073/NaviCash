"""tests — Instagram: OAuth (Instagram Login), webhook y bandeja de chats.

Cubre la Fase 2 de la mensajería:

- Handshake ``GET`` del webhook con el verify token global.
- ``POST`` firmado (HMAC ``X-Hub-Signature-256``): ingesta, deduplicación, ecos
  (mensajes salientes), ignorado de cuentas desconocidas y modo dev sin firma.
- Rehospedaje de adjuntos entrantes (la CDN de Meta caduca las URLs).
- OAuth: inicio (URL de autorización) y callback (canje de código + token).
- Endpoint de estado/desconexión de la cuenta.
- Envío saliente: texto, adjunto (multipart), ventana de 24 h y refresco.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import timedelta
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

import pytest
from django.core import signing
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.business.services import create_business
from apps.crm.instagram_service import (
    build_authorize_url,
    describe_inbound,
    extract_attachments,
    extract_events,
)
from apps.crm.models import (
    ChatAttachment,
    ChatConversation,
    ChatMessage,
    InstagramConfig,
)
from apps.crm.views import _OAUTH_STATE_SALT

WEBHOOK_URL = "/api/business/instagram/webhook/"
OAUTH_START_URL = "/api/business/instagram/oauth/start/"
OAUTH_CALLBACK_URL = "/api/business/instagram/oauth/callback/"
CONFIG_URL = "/api/business/instagram/config/"
CHATS_URL = "/api/business/chats/"

APP_ID = "1234567890"
APP_SECRET = "app-secret-value"
VERIFY_TOKEN = "verify-token-value"
ACCESS_TOKEN = "IGQVJ-token-de-prueba"


def _sign(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _inbound_payload(
    *,
    ig_id: str = "IG-BIZ-1",
    sender: str = "IGSID-42",
    recipient: str = "IG-BIZ-1",
    mid: str = "mid.ABC",
    text: str = "Hola",
    attachments: list | None = None,
    echo: bool = False,
) -> dict:
    """Payload de Instagram con un evento de mensajería (``entry[].messaging[]``)."""
    message: dict = {"mid": mid}
    if text:
        message["text"] = text
    if attachments is not None:
        message["attachments"] = attachments
    if echo:
        message["is_echo"] = True
    return {
        "object": "instagram",
        "entry": [
            {
                "id": ig_id,
                "time": 1700000000,
                "messaging": [
                    {
                        "sender": {"id": sender},
                        "recipient": {"id": recipient},
                        "timestamp": 1700000000,
                        "message": message,
                    }
                ],
            }
        ],
    }


def _post_webhook(client, payload: dict, *, secret: str | None = APP_SECRET, sign: bool = True):
    body = json.dumps(payload).encode("utf-8")
    headers = {}
    if sign:
        headers["HTTP_X_HUB_SIGNATURE_256"] = _sign(secret or "", body)
    return client.post(WEBHOOK_URL, data=body, content_type="application/json", **headers)


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict, content: bytes = b"", headers: dict | None = None):
        self.status_code = status_code
        self._payload = payload
        self.content = content
        self.headers = headers or {}

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def _ig_settings(settings):
    """Configura las credenciales globales de la app de Meta para los tests."""
    settings.INSTAGRAM_APP_ID = APP_ID
    settings.INSTAGRAM_APP_SECRET = APP_SECRET
    settings.INSTAGRAM_REDIRECT_URI = "http://testserver/api/business/instagram/oauth/callback/"
    settings.INSTAGRAM_VERIFY_TOKEN = VERIFY_TOKEN
    settings.APP_BASE_URL = "http://localhost:5173"


@pytest.fixture
def business(api_client):
    return create_business(
        api_client.user, name="Tienda Instagram", currency="USD", initial_capital=Decimal("0")
    )


@pytest.fixture
def ig_config(api_client, business):
    cfg = InstagramConfig(
        user=api_client.user,
        business=business,
        ig_user_id="IG-BIZ-1",
        username="tienda_demo",
    )
    cfg.access_token = ACCESS_TOKEN
    cfg.save()
    return cfg


# ---------------------------------------------------------------------------
# Lógica pura: parseo de eventos y adjuntos
# ---------------------------------------------------------------------------


class TestParsing:
    """Funciones puras de ``instagram_service`` (sin base de datos)."""

    def test_extract_events_flattens_messaging(self) -> None:
        events = extract_events(_inbound_payload(ig_id="IG-9", mid="mid.1"))
        assert len(events) == 1
        assert events[0]["ig_user_id"] == "IG-9"
        assert events[0]["mid"] == "mid.1"
        assert events[0]["is_echo"] is False

    def test_extract_events_ignores_non_messaging(self) -> None:
        payload = {"object": "instagram", "entry": [{"id": "IG-1", "changes": []}]}
        assert extract_events(payload) == []

    def test_describe_inbound_text(self) -> None:
        event = extract_events(_inbound_payload(text="Buenas"))[0]
        info = describe_inbound(event)
        assert info["external_id"] == "mid.ABC"
        assert info["from"] == "IGSID-42"
        assert info["type"] == "text"
        assert info["body"] == "Buenas"
        assert info["attachments"] == []

    def test_describe_inbound_attachment_placeholder(self) -> None:
        payload = _inbound_payload(
            text="",
            attachments=[{"type": "image", "payload": {"url": "https://cdn/x.jpg"}}],
        )
        info = describe_inbound(extract_events(payload)[0])
        assert info["type"] == "image"
        assert info["body"] == "[Imagen recibida]"
        assert info["attachments"] == [{"kind": "image", "url": "https://cdn/x.jpg"}]

    def test_describe_inbound_echo_flagged(self) -> None:
        payload = _inbound_payload(
            sender="IG-BIZ-1", recipient="IGSID-42", echo=True
        )
        info = describe_inbound(extract_events(payload)[0])
        assert info["is_echo"] is True

    def test_extract_attachments_skips_without_url(self) -> None:
        message = {"attachments": [{"type": "image", "payload": {}}]}
        assert extract_attachments(message) == []

    def test_build_authorize_url(self) -> None:
        url = build_authorize_url("state-abc")
        assert url.startswith("https://www.instagram.com/oauth/authorize?")
        assert f"client_id={APP_ID}" in url
        assert "instagram_business_manage_messages" in url
        assert "state-abc" in url
        assert "enable_fb_login=0" in url


# ---------------------------------------------------------------------------
# Handshake GET del webhook
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestWebhookVerification:
    def test_verify_returns_challenge(self, api_client) -> None:
        resp = api_client.get(
            WEBHOOK_URL,
            {"hub.mode": "subscribe", "hub.verify_token": VERIFY_TOKEN, "hub.challenge": "abc"},
        )
        assert resp.status_code == 200
        assert resp.content.decode() == "abc"

    def test_verify_wrong_token_forbidden(self, api_client) -> None:
        resp = api_client.get(
            WEBHOOK_URL,
            {"hub.mode": "subscribe", "hub.verify_token": "nope", "hub.challenge": "x"},
        )
        assert resp.status_code == 403

    def test_verify_without_configured_token_forbidden(self, api_client, settings) -> None:
        settings.INSTAGRAM_VERIFY_TOKEN = ""
        resp = api_client.get(
            WEBHOOK_URL,
            {"hub.mode": "subscribe", "hub.verify_token": "", "hub.challenge": "x"},
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST del webhook: ingesta de eventos
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestWebhookInbound:
    def test_invalid_signature_rejected(self, api_client, ig_config) -> None:
        resp = _post_webhook(api_client, _inbound_payload(), secret="otro")
        assert resp.status_code == 403
        assert ChatMessage.objects.count() == 0

    def test_missing_signature_rejected(self, api_client, ig_config) -> None:
        resp = _post_webhook(api_client, _inbound_payload(), sign=False)
        assert resp.status_code == 403

    def test_valid_signature_ingests_message(self, api_client, ig_config) -> None:
        resp = _post_webhook(api_client, _inbound_payload(text="Hola IG"))
        assert resp.status_code == 200
        conversation = ChatConversation.objects.get()
        assert conversation.platform == "instagram"
        assert conversation.external_id == "IGSID-42"
        assert conversation.unread_count == 1
        assert conversation.last_message_preview == "Hola IG"
        message = ChatMessage.objects.get()
        assert message.direction == "in"
        assert message.external_id == "mid.ABC"
        assert message.status == "received"

    def test_duplicate_mid_ignored(self, api_client, ig_config) -> None:
        _post_webhook(api_client, _inbound_payload())
        _post_webhook(api_client, _inbound_payload())
        assert ChatMessage.objects.count() == 1
        assert ChatConversation.objects.get().unread_count == 1

    def test_echo_is_outbound_without_unread(self, api_client, ig_config) -> None:
        _post_webhook(
            api_client,
            _inbound_payload(sender="IG-BIZ-1", recipient="IGSID-42", echo=True, text="Respuesta"),
        )
        conversation = ChatConversation.objects.get()
        assert conversation.external_id == "IGSID-42"
        assert conversation.unread_count == 0
        message = ChatMessage.objects.get()
        assert message.direction == "out"
        assert message.status == "sent"

    def test_unknown_account_ignored(self, api_client, ig_config) -> None:
        resp = _post_webhook(api_client, _inbound_payload(ig_id="IG-DESCONOCIDO"))
        assert resp.status_code == 200
        assert ChatConversation.objects.count() == 0

    def test_dev_mode_without_app_secret_skips_signature(self, api_client, ig_config, settings) -> None:
        settings.INSTAGRAM_APP_SECRET = ""
        resp = _post_webhook(api_client, _inbound_payload(), sign=False)
        assert resp.status_code == 200
        assert ChatMessage.objects.count() == 1

    def test_inbound_attachment_is_rehosted(self, api_client, ig_config, monkeypatch) -> None:
        def fake_get(url, **kwargs):
            return _FakeResponse(
                200,
                {},
                content=b"\xff\xd8\xff-imagen",
                headers={"content-type": "image/jpeg"},
            )

        monkeypatch.setattr("apps.crm.views.httpx.get", fake_get)

        payload = _inbound_payload(
            text="",
            attachments=[{"type": "image", "payload": {"url": "https://cdn.meta/img.jpg"}}],
        )
        resp = _post_webhook(api_client, payload)
        assert resp.status_code == 200
        attachment = ChatAttachment.objects.get()
        assert attachment.kind == "image"
        assert attachment.remote_url == "https://cdn.meta/img.jpg"
        assert attachment.filename == "img.jpg"
        assert attachment.mime == "image/jpeg"
        assert attachment.size == len(b"\xff\xd8\xff-imagen")
        assert attachment.file.name.endswith(".jpg")

    def test_inbound_attachment_keeps_remote_url_on_failure(self, api_client, ig_config, monkeypatch) -> None:
        import httpx as _httpx

        def raising_get(url, **kwargs):
            raise _httpx.ConnectError("sin red")

        monkeypatch.setattr("apps.crm.views.httpx.get", raising_get)

        payload = _inbound_payload(
            text="",
            attachments=[{"type": "file", "payload": {"url": "https://cdn.meta/doc.pdf"}}],
        )
        resp = _post_webhook(api_client, payload)
        assert resp.status_code == 200
        attachment = ChatAttachment.objects.get()
        assert attachment.kind == "file"
        assert attachment.remote_url == "https://cdn.meta/doc.pdf"
        assert not attachment.file

    def test_invalid_json_returns_400(self, api_client) -> None:
        resp = api_client.post(WEBHOOK_URL, data=b"not-json", content_type="application/json")
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# OAuth (Instagram Login)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestInstagramOAuth:
    def test_start_requires_auth(self) -> None:
        from rest_framework.test import APIClient

        resp = APIClient().get(OAUTH_START_URL)
        assert resp.status_code == 401

    def test_start_returns_authorize_url(self, api_client) -> None:
        resp = api_client.get(OAUTH_START_URL)
        assert resp.status_code == 200
        assert resp.data["authorize_url"].startswith("https://www.instagram.com/oauth/authorize?")

    def test_start_not_configured(self, api_client, settings) -> None:
        settings.INSTAGRAM_APP_ID = ""
        resp = api_client.get(OAUTH_START_URL)
        assert resp.status_code == 400
        assert resp.data["code"] == "instagram_not_configured"

    def test_callback_connects_account(self, api_client, business, monkeypatch) -> None:
        def fake_post(url, data=None, json=None, headers=None, timeout=None):
            assert "oauth/access_token" in url
            assert data["code"] == "the-code"
            return _FakeResponse(
                200,
                {"access_token": "short", "user_id": "IG-BIZ-9", "permissions": ["instagram_business_basic"]},
            )

        def fake_get(url, params=None, timeout=None, **kwargs):
            if "refresh_access_token" in url:
                return _FakeResponse(200, {"access_token": "refreshed", "expires_in": 5184000})
            if url.endswith("/access_token"):
                return _FakeResponse(200, {"access_token": "long-lived", "expires_in": 5184000})
            return _FakeResponse(
                200,
                {"id": "IG-BIZ-9", "username": "tienda_real", "name": "Tienda", "profile_picture_url": "http://x/p.jpg"},
            )

        monkeypatch.setattr("apps.crm.instagram_service.httpx.post", fake_post)
        monkeypatch.setattr("apps.crm.instagram_service.httpx.get", fake_get)

        state = signing.dumps({"uid": api_client.user.id}, salt=_OAUTH_STATE_SALT, compress=True)
        resp = api_client.get(OAUTH_CALLBACK_URL, {"code": "the-code", "state": state})
        assert resp.status_code == 200
        assert resp.headers["Content-Type"].startswith("text/html")
        body = resp.content.decode()
        assert "instagram=connected" in body
        assert "window.location.replace" in body

        config = InstagramConfig.objects.get(user=api_client.user)
        assert config.ig_user_id == "IG-BIZ-9"
        assert config.username == "tienda_real"
        assert config.access_token == "long-lived"
        assert config.access_token_encrypted != "long-lived"
        assert config.token_expires_at is not None

    def test_start_popup_mode_embeds_mode_in_state(self, api_client) -> None:
        resp = api_client.get(OAUTH_START_URL, {"mode": "popup"})
        assert resp.status_code == 200
        query = urlparse(resp.data["authorize_url"]).query
        state = parse_qs(query)["state"][0]
        assert signing.loads(state, salt=_OAUTH_STATE_SALT)["mode"] == "popup"

    def test_callback_popup_mode_closes_window(self, api_client, business, monkeypatch) -> None:
        def fake_post(url, data=None, json=None, headers=None, timeout=None):
            return _FakeResponse(
                200,
                {"access_token": "short", "user_id": "IG-BIZ-9", "permissions": ["instagram_business_basic"]},
            )

        def fake_get(url, params=None, timeout=None, **kwargs):
            if "refresh_access_token" in url:
                return _FakeResponse(200, {"access_token": "refreshed", "expires_in": 5184000})
            if url.endswith("/access_token"):
                return _FakeResponse(200, {"access_token": "long-lived", "expires_in": 5184000})
            return _FakeResponse(200, {"id": "IG-BIZ-9", "username": "tienda_real"})

        monkeypatch.setattr("apps.crm.instagram_service.httpx.post", fake_post)
        monkeypatch.setattr("apps.crm.instagram_service.httpx.get", fake_get)

        state = signing.dumps(
            {"uid": api_client.user.id, "mode": "popup"},
            salt=_OAUTH_STATE_SALT,
            compress=True,
        )
        resp = api_client.get(OAUTH_CALLBACK_URL, {"code": "the-code", "state": state})
        assert resp.status_code == 200
        assert resp.headers["Content-Type"].startswith("text/html")
        body = resp.content.decode()
        assert "window.close()" in body
        assert "window.location.replace" not in body

    def test_callback_bad_state_returns_error(self, api_client, business) -> None:
        resp = api_client.get(OAUTH_CALLBACK_URL, {"code": "x", "state": "invalido"})
        assert resp.status_code == 200
        assert "instagram=error" in resp.content.decode()
        assert InstagramConfig.objects.count() == 0

    def test_callback_exchange_failure_returns_error(self, api_client, business, monkeypatch) -> None:
        def fake_post(*args, **kwargs):
            return _FakeResponse(400, {"error": {"message": "bad code"}})

        monkeypatch.setattr("apps.crm.instagram_service.httpx.post", fake_post)
        state = signing.dumps({"uid": api_client.user.id}, salt=_OAUTH_STATE_SALT, compress=True)
        resp = api_client.get(OAUTH_CALLBACK_URL, {"code": "x", "state": state})
        assert resp.status_code == 200
        assert "instagram=error" in resp.content.decode()
        assert InstagramConfig.objects.count() == 0

    def test_callback_requires_business(self, api_client, monkeypatch) -> None:
        state = signing.dumps({"uid": api_client.user.id}, salt=_OAUTH_STATE_SALT, compress=True)
        resp = api_client.get(OAUTH_CALLBACK_URL, {"code": "x", "state": state})
        assert resp.status_code == 200
        assert "instagram=error" in resp.content.decode()


# ---------------------------------------------------------------------------
# Estado de la conexión
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestInstagramConfig:
    def test_get_without_config_reports_disconnected(self, api_client) -> None:
        resp = api_client.get(CONFIG_URL)
        assert resp.status_code == 200
        assert resp.data["connected"] is False

    def test_get_never_returns_raw_secret(self, api_client, ig_config) -> None:
        resp = api_client.get(CONFIG_URL)
        assert resp.status_code == 200
        assert resp.data["connected"] is True
        assert resp.data["has_access_token"] is True
        assert ACCESS_TOKEN not in json.dumps(resp.data)
        assert "access_token_encrypted" not in resp.data

    def test_delete_config(self, api_client, ig_config) -> None:
        resp = api_client.delete(CONFIG_URL)
        assert resp.status_code == 204
        assert InstagramConfig.objects.filter(user=api_client.user).count() == 0

    def test_delete_without_config_404(self, api_client) -> None:
        resp = api_client.delete(CONFIG_URL)
        assert resp.status_code == 404

    def test_owner_isolation(self, api_client, ig_config, auth_client_factory) -> None:
        other = auth_client_factory()
        resp = other.get(CONFIG_URL)
        assert resp.status_code == 200
        assert resp.data["connected"] is False


# ---------------------------------------------------------------------------
# Bandeja: envío saliente por Instagram
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestInstagramSend:
    @pytest.fixture
    def conversation(self, api_client, business):
        return ChatConversation.objects.create(
            user=api_client.user,
            business=business,
            platform="instagram",
            external_id="IGSID-42",
        )

    def test_send_text_requires_content(self, api_client, conversation, ig_config) -> None:
        resp = api_client.post(f"{CHATS_URL}{conversation.id}/send/", {}, format="json")
        assert resp.status_code == 400

    def test_send_without_connection(self, api_client, conversation) -> None:
        resp = api_client.post(
            f"{CHATS_URL}{conversation.id}/send/", {"text": "Hola"}, format="json"
        )
        assert resp.status_code == 400
        assert resp.data["code"] == "instagram_not_connected"

    def test_send_text_success(self, api_client, conversation, ig_config, monkeypatch) -> None:
        captured: dict = {}

        def fake_post(url, json, headers=None, timeout=None, **kwargs):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return _FakeResponse(200, {"message_id": "mid.OUT1"})

        monkeypatch.setattr("apps.crm.instagram_service.httpx.post", fake_post)

        resp = api_client.post(
            f"{CHATS_URL}{conversation.id}/send/", {"text": "Hola cliente"}, format="json"
        )
        assert resp.status_code == 201
        assert resp.data["direction"] == "out"
        message = ChatMessage.objects.get(direction="out")
        assert message.external_id == "mid.OUT1"
        assert message.body == "Hola cliente"
        assert captured["json"]["recipient"] == {"id": "IGSID-42"}
        assert captured["headers"]["Authorization"] == f"Bearer {ACCESS_TOKEN}"

    def test_send_window_closed(self, api_client, conversation, ig_config, monkeypatch) -> None:
        def fake_post(*args, **kwargs):
            return _FakeResponse(400, {"error": {"code": 10, "error_subcode": 2018278}})

        monkeypatch.setattr("apps.crm.instagram_service.httpx.post", fake_post)
        resp = api_client.post(
            f"{CHATS_URL}{conversation.id}/send/", {"text": "Hola"}, format="json"
        )
        assert resp.status_code == 400
        assert resp.data["code"] == "instagram_window_closed"
        assert ChatMessage.objects.filter(direction="out").count() == 0

    def test_send_attachment_success(self, api_client, conversation, ig_config, monkeypatch) -> None:
        captured: dict = {}

        def fake_post(url, json, headers=None, timeout=None, **kwargs):
            captured["json"] = json
            return _FakeResponse(200, {"message_id": "mid.IMG"})

        monkeypatch.setattr("apps.crm.instagram_service.httpx.post", fake_post)

        upload = SimpleUploadedFile("foto.jpg", b"\xff\xd8\xff-data", content_type="image/jpeg")
        resp = api_client.post(
            f"{CHATS_URL}{conversation.id}/send/", {"file": upload}, format="multipart"
        )
        assert resp.status_code == 201
        assert resp.data["message_type"] == "image"
        assert len(resp.data["attachments"]) == 1
        assert captured["json"]["message"]["attachment"]["type"] == "image"
        assert captured["json"]["message"]["attachment"]["payload"]["url"]
        attachment = ChatAttachment.objects.get()
        assert attachment.kind == "image"
        assert attachment.file

    def test_send_attachment_failure_rolls_back(self, api_client, conversation, ig_config, monkeypatch) -> None:
        def fake_post(*args, **kwargs):
            return _FakeResponse(400, {"error": {"code": 10, "error_subcode": 2534022}})

        monkeypatch.setattr("apps.crm.instagram_service.httpx.post", fake_post)
        upload = SimpleUploadedFile("clip.mp4", b"data", content_type="video/mp4")
        resp = api_client.post(
            f"{CHATS_URL}{conversation.id}/send/", {"file": upload}, format="multipart"
        )
        assert resp.status_code == 400
        assert resp.data["code"] == "instagram_window_closed"
        assert ChatMessage.objects.filter(direction="out").count() == 0
        assert ChatAttachment.objects.count() == 0

    def test_token_refreshed_when_near_expiry(self, api_client, conversation, ig_config, monkeypatch) -> None:
        ig_config.token_expires_at = timezone.now() + timedelta(days=1)
        ig_config.save(update_fields=["token_expires_at"])

        monkeypatch.setattr(
            "apps.crm.views.refresh_long_lived",
            lambda token: {"access_token": "renovado", "expires_in": 5184000},
        )
        monkeypatch.setattr(
            "apps.crm.instagram_service.httpx.post",
            lambda *a, **k: _FakeResponse(200, {"message_id": "mid.X"}),
        )

        resp = api_client.post(
            f"{CHATS_URL}{conversation.id}/send/", {"text": "Hola"}, format="json"
        )
        assert resp.status_code == 201
        ig_config.refresh_from_db()
        assert ig_config.access_token == "renovado"

    def test_messages_include_attachments(self, api_client, conversation, ig_config) -> None:
        message = ChatMessage.objects.create(
            user=api_client.user,
            conversation=conversation,
            direction="in",
            message_type="image",
            body="[Imagen recibida]",
        )
        attachment = ChatAttachment(
            user=api_client.user, message=message, kind="image", remote_url="https://cdn/x.jpg"
        )
        attachment.file.save("x.jpg", SimpleUploadedFile("x.jpg", b"data"), save=True)

        resp = api_client.get(f"{CHATS_URL}{conversation.id}/messages/")
        assert resp.status_code == 200
        item = resp.data["results"][0]
        assert len(item["attachments"]) == 1
        assert item["attachments"][0]["kind"] == "image"
