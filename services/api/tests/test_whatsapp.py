"""tests — WhatsApp: webhook de Meta, configuración y bandeja de chats.

Cubre la Fase 1 de la mensajería (inbox manual):

- Handshake ``GET`` del webhook (verificación de Meta).
- ``POST`` firmado (HMAC ``X-Hub-Signature-256``): ingesta, deduplicación,
  estados de entrega, ignorado de números desconocidos y modo dev sin firma.
- Endpoint de configuración (secretos cifrados, enmascarado, aislamiento).
- Bandeja: listado por dueño, marcado de leído y respuesta manual (éxito,
  ventana de 24 h y sin conexión), con ``httpx.post`` simulado.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.business.services import create_business
from apps.crm.models import (
    BusinessContact,
    ChatConversation,
    ChatMessage,
    WhatsAppConfig,
)
from apps.crm.whatsapp_service import (
    describe_inbound,
    extract_changes,
    verify_signature,
)

WEBHOOK_URL = "/api/business/whatsapp/webhook/"
CONFIG_URL = "/api/business/whatsapp/config/"
CHATS_URL = "/api/business/chats/"

APP_SECRET = "app-secret-value"
ACCESS_TOKEN = "EAAG-token-de-prueba"


def _sign(secret: str, body: bytes) -> str:
    """Firma HMAC-SHA256 del cuerpo con el formato que envía Meta."""
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _inbound_payload(
    *,
    phone_number_id: str = "123456",
    wa_id: str = "584141234567",
    wamid: str = "wamid.ABC",
    text: str = "Hola",
    name: str = "Cliente Demo",
) -> dict:
    """Payload de Meta con un mensaje de texto entrante."""
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA-ID",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "584000000000",
                                "phone_number_id": phone_number_id,
                            },
                            "contacts": [{"profile": {"name": name}, "wa_id": wa_id}],
                            "messages": [
                                {
                                    "from": wa_id,
                                    "id": wamid,
                                    "timestamp": "1700000000",
                                    "type": "text",
                                    "text": {"body": text},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


def _post_webhook(client, payload: dict, *, secret: str | None = APP_SECRET, sign: bool = True):
    """POST del webhook con firma opcional del cuerpo crudo."""
    body = json.dumps(payload).encode("utf-8")
    headers = {}
    if sign:
        headers["HTTP_X_HUB_SIGNATURE_256"] = _sign(secret or "", body)
    return client.post(WEBHOOK_URL, data=body, content_type="application/json", **headers)


@pytest.fixture
def business(api_client):
    """Negocio del usuario autenticado."""
    return create_business(
        api_client.user, name="Tienda WhatsApp", currency="USD", initial_capital=Decimal("0")
    )


@pytest.fixture
def config(api_client, business):
    """Credenciales de WhatsApp conectadas del usuario autenticado."""
    cfg = WhatsAppConfig(
        user=api_client.user,
        business=business,
        phone_number_id="123456",
        display_phone_number="584000000000",
    )
    cfg.access_token = ACCESS_TOKEN
    cfg.app_secret = APP_SECRET
    cfg.save()
    return cfg


# ---------------------------------------------------------------------------
# Lógica pura: firma, parseo y resumen de entrantes
# ---------------------------------------------------------------------------


class TestSignatureAndParsing:
    """Funciones puras de ``whatsapp_service`` (sin base de datos)."""

    def test_verify_signature_ok(self) -> None:
        body = b'{"a":1}'
        assert verify_signature(APP_SECRET, body, _sign(APP_SECRET, body)) is True

    def test_verify_signature_bad(self) -> None:
        assert verify_signature(APP_SECRET, b'{"a":1}', "sha256=deadbeef") is False

    def test_verify_signature_without_secret_is_dev_open(self) -> None:
        assert verify_signature("", b"cualquiera", "") is True

    def test_verify_signature_missing_header(self) -> None:
        assert verify_signature(APP_SECRET, b"x", "") is False

    def test_extract_changes_flattens_entries(self) -> None:
        payload = _inbound_payload(phone_number_id="999")
        changes = extract_changes(payload)
        assert len(changes) == 1
        assert changes[0]["phone_number_id"] == "999"
        assert changes[0]["field"] == "messages"

    def test_describe_inbound_text(self) -> None:
        info = describe_inbound(
            {"id": "wamid.1", "from": "584141234567", "type": "text", "text": {"body": "Hola"}}
        )
        assert info == {
            "external_id": "wamid.1",
            "from": "584141234567",
            "type": "text",
            "body": "Hola",
        }

    def test_describe_inbound_unknown_type_uses_placeholder(self) -> None:
        info = describe_inbound({"id": "w", "from": "1", "type": "image"})
        assert info["body"] == "[Imagen recibida]"


# ---------------------------------------------------------------------------
# Handshake GET del webhook
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestWebhookVerification:
    """GET /api/business/whatsapp/webhook/ (verificación de Meta)."""

    def test_verify_returns_challenge(self, api_client, config) -> None:
        resp = api_client.get(
            WEBHOOK_URL,
            {
                "hub.mode": "subscribe",
                "hub.verify_token": config.verify_token,
                "hub.challenge": "abc123",
            },
        )
        assert resp.status_code == 200
        assert resp.content.decode() == "abc123"

    def test_verify_wrong_token_forbidden(self, api_client, config) -> None:
        resp = api_client.get(
            WEBHOOK_URL,
            {"hub.mode": "subscribe", "hub.verify_token": "nope", "hub.challenge": "x"},
        )
        assert resp.status_code == 403

    def test_verify_missing_mode_forbidden(self, api_client, config) -> None:
        resp = api_client.get(
            WEBHOOK_URL,
            {"hub.verify_token": config.verify_token, "hub.challenge": "x"},
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST del webhook: ingesta de eventos
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestWebhookInbound:
    """POST /api/business/whatsapp/webhook/ (entrega de eventos)."""

    def test_invalid_signature_rejected(self, api_client, config) -> None:
        resp = _post_webhook(api_client, _inbound_payload(), secret="otro-secreto")
        assert resp.status_code == 403
        assert ChatMessage.objects.count() == 0

    def test_missing_signature_rejected(self, api_client, config) -> None:
        resp = _post_webhook(api_client, _inbound_payload(), sign=False)
        assert resp.status_code == 403

    def test_valid_signature_ingests_message(self, api_client, config) -> None:
        resp = _post_webhook(api_client, _inbound_payload(text="Buenos días"))
        assert resp.status_code == 200

        conversation = ChatConversation.objects.get(user=api_client.user)
        assert conversation.external_id == "584141234567"
        assert conversation.contact_name == "Cliente Demo"
        assert conversation.last_message_preview == "Buenos días"
        assert conversation.unread_count == 1

        message = ChatMessage.objects.get()
        assert message.direction == "in"
        assert message.body == "Buenos días"
        assert message.external_id == "wamid.ABC"
        assert message.status == "received"

    def test_duplicate_wamid_is_ignored(self, api_client, config) -> None:
        _post_webhook(api_client, _inbound_payload())
        _post_webhook(api_client, _inbound_payload())
        assert ChatMessage.objects.count() == 1
        conversation = ChatConversation.objects.get()
        assert conversation.unread_count == 1

    def test_second_message_increments_unread(self, api_client, config) -> None:
        _post_webhook(api_client, _inbound_payload(wamid="wamid.1", text="uno"))
        _post_webhook(api_client, _inbound_payload(wamid="wamid.2", text="dos"))
        conversation = ChatConversation.objects.get()
        assert conversation.unread_count == 2
        assert conversation.last_message_preview == "dos"

    def test_unknown_number_is_ignored(self, api_client, config) -> None:
        resp = _post_webhook(api_client, _inbound_payload(phone_number_id="000000"))
        assert resp.status_code == 200
        assert ChatConversation.objects.count() == 0

    def test_inbound_links_directory_contact(self, api_client, business, config) -> None:
        contact = BusinessContact.objects.create(
            user=api_client.user,
            business=business,
            name="Ana",
            type="cliente",
            phone="+58 414-1234567",
        )
        _post_webhook(api_client, _inbound_payload(wa_id="584141234567"))
        conversation = ChatConversation.objects.get()
        assert conversation.contact_id == contact.id

    def test_dev_mode_without_app_secret_skips_signature(self, api_client, business) -> None:
        cfg = WhatsAppConfig(
            user=api_client.user, business=business, phone_number_id="123456"
        )
        cfg.access_token = ACCESS_TOKEN
        cfg.save()

        resp = _post_webhook(api_client, _inbound_payload(), sign=False)
        assert resp.status_code == 200
        assert ChatMessage.objects.count() == 1

    def test_status_update_marks_outbound_message(self, api_client, config) -> None:
        conversation = ChatConversation.objects.create(
            user=api_client.user,
            business=config.business,
            platform="whatsapp",
            external_id="584141234567",
        )
        message = ChatMessage.objects.create(
            user=api_client.user,
            conversation=conversation,
            external_id="wamid.OUT",
            direction="out",
            body="Respuesta",
            status="sent",
        )
        payload = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "WABA-ID",
                    "changes": [
                        {
                            "field": "messages",
                            "value": {
                                "messaging_product": "whatsapp",
                                "metadata": {"phone_number_id": "123456"},
                                "statuses": [
                                    {
                                        "id": "wamid.OUT",
                                        "status": "delivered",
                                        "recipient_id": "584141234567",
                                    }
                                ],
                            },
                        }
                    ],
                }
            ],
        }
        resp = _post_webhook(api_client, payload)
        assert resp.status_code == 200
        message.refresh_from_db()
        assert message.status == "delivered"

    def test_invalid_json_returns_400(self, api_client) -> None:
        resp = api_client.post(
            WEBHOOK_URL, data=b"not-json", content_type="application/json"
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Configuración de WhatsApp
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestWhatsAppConfig:
    """GET/POST/DELETE /api/business/whatsapp/config/."""

    def test_get_without_config_reports_disconnected(self, api_client) -> None:
        resp = api_client.get(CONFIG_URL)
        assert resp.status_code == 200
        assert resp.data["connected"] is False

    def test_create_masks_and_encrypts_secrets(self, api_client, business) -> None:
        resp = api_client.post(
            CONFIG_URL,
            {
                "phone_number_id": "111222",
                "display_phone_number": "584001112222",
                "access_token": ACCESS_TOKEN,
                "app_secret": APP_SECRET,
            },
            format="json",
        )
        assert resp.status_code == 200
        assert resp.data["connected"] is True
        assert resp.data["has_access_token"] is True
        assert resp.data["has_app_secret"] is True
        assert "access_token" not in resp.data
        assert "app_secret" not in resp.data
        assert ACCESS_TOKEN not in json.dumps(resp.data)
        assert resp.data["verify_token"]

        cfg = WhatsAppConfig.objects.get(user=api_client.user)
        assert cfg.access_token == ACCESS_TOKEN
        assert cfg.app_secret == APP_SECRET
        assert cfg.access_token_encrypted != ACCESS_TOKEN
        assert cfg.app_secret_encrypted != APP_SECRET
        assert ACCESS_TOKEN not in cfg.access_token_encrypted

    def test_get_never_returns_raw_secrets(self, api_client, config) -> None:
        resp = api_client.get(CONFIG_URL)
        assert resp.status_code == 200
        assert resp.data["connected"] is True
        assert "access_token" not in resp.data
        assert "app_secret" not in resp.data
        assert ACCESS_TOKEN not in json.dumps(resp.data)

    def test_requires_business(self, api_client) -> None:
        resp = api_client.post(CONFIG_URL, {"phone_number_id": "111"}, format="json")
        assert resp.status_code == 400
        assert resp.data["code"] == "validation_error"

    def test_update_keeps_secret_when_omitted(self, api_client, business, config) -> None:
        resp = api_client.post(
            CONFIG_URL, {"display_phone_number": "584009998888"}, format="json"
        )
        assert resp.status_code == 200
        config.refresh_from_db()
        assert config.display_phone_number == "584009998888"
        assert config.access_token == ACCESS_TOKEN

    def test_duplicate_number_rejected(self, api_client, business, auth_client_factory) -> None:
        # El usuario A conecta el número 565656.
        cfg = WhatsAppConfig(
            user=api_client.user, business=business, phone_number_id="565656"
        )
        cfg.save()

        # El usuario B intenta reusar el mismo phone_number_id: choca con la
        # restricción única global y la vista lo traduce a 400 legible.
        other_client = auth_client_factory()
        create_business(
            other_client.user, name="Otro", currency="USD", initial_capital=Decimal("0")
        )
        resp = other_client.post(CONFIG_URL, {"phone_number_id": "565656"}, format="json")
        assert resp.status_code == 400
        assert resp.data["code"] == "validation_error"

    def test_owner_isolation(self, api_client, business, config, auth_client_factory) -> None:
        other_client = auth_client_factory()
        resp = other_client.get(CONFIG_URL)
        assert resp.status_code == 200
        assert resp.data["connected"] is False

    def test_delete_config(self, api_client, config) -> None:
        resp = api_client.delete(CONFIG_URL)
        assert resp.status_code == 204
        assert WhatsAppConfig.objects.filter(user=api_client.user).count() == 0

    def test_delete_without_config_404(self, api_client) -> None:
        resp = api_client.delete(CONFIG_URL)
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Bandeja de conversaciones
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestChatInbox:
    """GET /api/business/chats/ y sus acciones ``messages`` / ``send``."""

    @pytest.fixture
    def conversation(self, api_client, business):
        return ChatConversation.objects.create(
            user=api_client.user,
            business=business,
            platform="whatsapp",
            external_id="584141234567",
            contact_name="Cliente Demo",
            unread_count=3,
            last_message_at=timezone.now(),
        )

    def test_list_scoped_to_owner(self, api_client, conversation, auth_client_factory) -> None:
        other_client = auth_client_factory()
        other_business = create_business(
            other_client.user, name="Otro", currency="USD", initial_capital=Decimal("0")
        )
        ChatConversation.objects.create(
            user=other_client.user,
            business=other_business,
            platform="whatsapp",
            external_id="584000000000",
        )
        resp = api_client.get(CHATS_URL)
        assert resp.status_code == 200
        assert len(resp.data["results"]) == 1
        assert resp.data["results"][0]["external_id"] == "584141234567"

    def test_messages_returns_and_marks_read(self, api_client, conversation) -> None:
        ChatMessage.objects.create(
            user=api_client.user, conversation=conversation, direction="in", body="Hola"
        )
        resp = api_client.get(f"{CHATS_URL}{conversation.id}/messages/")
        assert resp.status_code == 200
        assert resp.data["results"][0]["body"] == "Hola"
        conversation.refresh_from_db()
        assert conversation.unread_count == 0

    def test_send_requires_text(self, api_client, conversation) -> None:
        resp = api_client.post(
            f"{CHATS_URL}{conversation.id}/send/", {"text": "   "}, format="json"
        )
        assert resp.status_code == 400

    def test_send_without_connection(self, api_client, conversation) -> None:
        resp = api_client.post(
            f"{CHATS_URL}{conversation.id}/send/", {"text": "Hola"}, format="json"
        )
        assert resp.status_code == 400
        assert resp.data["code"] == "whatsapp_not_connected"

    def test_send_success(self, api_client, conversation, config, monkeypatch) -> None:
        captured: dict = {}

        class FakeResponse:
            status_code = 200

            def json(self):
                return {"messages": [{"id": "wamid.OUT1"}]}

        def fake_post(url, json, headers, timeout):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return FakeResponse()

        monkeypatch.setattr("apps.crm.whatsapp_service.httpx.post", fake_post)

        resp = api_client.post(
            f"{CHATS_URL}{conversation.id}/send/", {"text": "Hola cliente"}, format="json"
        )
        assert resp.status_code == 201
        assert resp.data["direction"] == "out"

        message = ChatMessage.objects.get(direction="out")
        assert message.external_id == "wamid.OUT1"
        assert message.body == "Hola cliente"
        assert captured["json"]["to"] == "584141234567"
        assert captured["headers"]["Authorization"] == f"Bearer {ACCESS_TOKEN}"

        conversation.refresh_from_db()
        assert conversation.last_message_preview == "Hola cliente"

    def test_send_window_closed(self, api_client, conversation, config, monkeypatch) -> None:
        class FakeResponse:
            status_code = 400

            def json(self):
                return {"error": {"code": 131047, "message": "window closed"}}

        monkeypatch.setattr(
            "apps.crm.whatsapp_service.httpx.post", lambda *a, **k: FakeResponse()
        )

        resp = api_client.post(
            f"{CHATS_URL}{conversation.id}/send/", {"text": "Hola"}, format="json"
        )
        assert resp.status_code == 400
        assert resp.data["code"] == "whatsapp_window_closed"
        assert ChatMessage.objects.filter(direction="out").count() == 0
