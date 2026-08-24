"""tests — Web Push: suscripciones, token interno, tick y recordatorio diario."""

from __future__ import annotations

import json
from datetime import date, datetime, time as dt_time, timedelta, timezone as dt_timezone
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.core.cache import cache
from pywebpush import WebPushException
from rest_framework.test import APIClient

import pytest

from apps.notifications.models import Notification, PushSubscription
from apps.notifications.services import (
    TICK_LOCK_KEY,
    _notify_missing,
    nudge_candidate,
    tick,
)
from factories import TransactionFactory, UserFactory

#: Configuración VAPID/token para TODA esta suite. El nudge queda apagado por
#: defecto (hora 24: ningún momento local la supera) para no contaminar los
#: conteos de los tests de vencimientos; los tests del nudge lo encienden.
PUSH_SETTINGS = {
    "VAPID_PUBLIC_KEY": "BTestPublicKey",
    "VAPID_PRIVATE_KEY": "test-private-key",
    "VAPID_SUBJECT": "mailto:test@example.com",
    "INTERNAL_TOKEN": "super-secret-token",
    "NUDGE_LOCAL_HOUR": 24,
}


@pytest.fixture(autouse=True)
def _push_settings(settings):
    """Aplica VAPID/token/toggles de la suite a cada test (restaurados al salir)."""
    for key, value in PUSH_SETTINGS.items():
        setattr(settings, key, value)


def _yesterday() -> date:
    return date.today() - timedelta(days=1)


def _make_sub(user, n: int = 1) -> PushSubscription:
    return PushSubscription.objects.create(
        user=user,
        endpoint=f"https://fcm.googleapis.com/fcm/send/test-endpoint-{n}",
        p256dh=f"p256dh-key-{n}",
        auth=f"auth-secret-{n}",
    )


def _payloads(mock_webpush) -> list[dict]:
    """Payloads JSON enviados al mock de ``webpush``, en orden."""
    return [json.loads(call.kwargs["data"]) for call in mock_webpush.call_args_list]


@pytest.mark.django_db
class TestPushSubscriptionEndpoints:
    """GET /api/push/vapid-key y POST/DELETE /api/push/subscriptions."""

    def test_vapid_key_requires_auth(self) -> None:
        resp = APIClient().get("/api/push/vapid-key")
        assert resp.status_code == 401

    def test_vapid_key_returned(self, api_client) -> None:
        resp = api_client.get("/api/push/vapid-key")
        assert resp.status_code == 200
        assert resp.data["publicKey"] == "BTestPublicKey"

    def test_vapid_key_503_when_unconfigured(self, api_client) -> None:
        from django.test import override_settings

        with override_settings(VAPID_PUBLIC_KEY=""):
            resp = api_client.get("/api/push/vapid-key")
        assert resp.status_code == 503

    def test_subscribe_creates(self, api_client) -> None:
        resp = api_client.post(
            "/api/push/subscriptions",
            {
                "endpoint": "https://fcm.googleapis.com/fcm/send/abc",
                "keys": {"p256dh": "k-p256dh", "auth": "k-auth"},
            },
            format="json",
        )
        assert resp.status_code == 201
        sub = PushSubscription.objects.get(
            user=api_client.user, endpoint="https://fcm.googleapis.com/fcm/send/abc"
        )
        assert sub.p256dh == "k-p256dh"
        assert sub.auth == "k-auth"

    def test_subscribe_upsert_same_endpoint(self, api_client) -> None:
        body = {
            "endpoint": "https://fcm.googleapis.com/fcm/send/abc",
            "keys": {"p256dh": "old", "auth": "old"},
        }
        api_client.post("/api/push/subscriptions", body, format="json")
        body["keys"] = {"p256dh": "new", "auth": "new"}
        api_client.post("/api/push/subscriptions", body, format="json")
        assert PushSubscription.objects.filter(user=api_client.user).count() == 1
        sub = PushSubscription.objects.get(user=api_client.user)
        assert (sub.p256dh, sub.auth) == ("new", "new")

    def test_subscribe_rejects_missing_keys(self, api_client) -> None:
        resp = api_client.post(
            "/api/push/subscriptions",
            {"endpoint": "https://fcm.googleapis.com/fcm/send/x", "keys": {}},
            format="json",
        )
        assert resp.status_code == 400

    def test_unsubscribe_removes(self, api_client) -> None:
        _make_sub(api_client.user)
        resp = api_client.delete(
            "/api/push/subscriptions",
            {"endpoint": "https://fcm.googleapis.com/fcm/send/test-endpoint-1"},
            format="json",
        )
        assert resp.status_code == 200
        assert PushSubscription.objects.filter(user=api_client.user).count() == 0

    def test_unsubscribe_unknown_404(self, api_client) -> None:
        resp = api_client.delete(
            "/api/push/subscriptions",
            {"endpoint": "https://fcm.googleapis.com/fcm/send/nope"},
            format="json",
        )
        assert resp.status_code == 404


@pytest.mark.django_db
class TestInternalTickEndpoint:
    """POST /api/internal/tick con X-Internal-Token."""

    FULL_URL = "/api/internal/tick"

    def _post(self, token: str | None):
        client = APIClient()
        kwargs = {} if token is None else {"HTTP_X_INTERNAL_TOKEN": token}
        return client.post(self.FULL_URL, **kwargs)

    def test_rejects_without_or_wrong_token(self) -> None:
        assert self._post(None).status_code == 403
        assert self._post("wrong-token").status_code == 403

    def test_rejects_when_token_unconfigured(self) -> None:
        # INTERNAL_TOKEN vacío deshabilita el endpoint aunque alguien envíe "".
        from django.test import override_settings

        with override_settings(INTERNAL_TOKEN=""):
            assert self._post("").status_code == 403

    def test_conflict_while_previous_cycle_running(self) -> None:
        cache.set(TICK_LOCK_KEY, 1, timeout=60)
        try:
            resp = self._post(PUSH_SETTINGS["INTERNAL_TOKEN"])
        finally:
            cache.delete(TICK_LOCK_KEY)
        assert resp.status_code == 409

    def test_pushes_only_new_alerts(self, api_client) -> None:
        TransactionFactory(
            user=api_client.user, fecha=_yesterday(), fecha_vencimiento=_yesterday()
        )
        _make_sub(api_client.user)
        token = PUSH_SETTINGS["INTERNAL_TOKEN"]
        with patch("apps.notifications.services.webpush") as mock_send:
            first = self._post(token)
            second = self._post(token)
        assert first.status_code == 200
        assert first.data == {"users": 1, "pushed": 1}
        assert second.status_code == 200
        assert second.data["pushed"] == 0
        assert mock_send.call_count == 1


@pytest.mark.django_db
class TestTickService:
    """tick() directo: entrega, poda 410, cap y aislamiento."""

    def _overdue_tx(self, user, concepto: str = "Prueba") -> None:
        TransactionFactory(
            user=user,
            concepto=concepto,
            fecha=_yesterday(),
            fecha_vencimiento=_yesterday(),
        )

    def test_delivers_overdue_once(self) -> None:
        user = UserFactory()
        self._overdue_tx(user)
        _make_sub(user)
        with patch("apps.notifications.services.webpush") as mock_send:
            result = tick()
        assert result == {"users": 1, "pushed": 1}
        payloads = _payloads(mock_send)
        assert len(payloads) == 1
        assert payloads[0]["kind"] == "overdue"
        assert payloads[0]["url"] == "/"
        assert "«" in payloads[0]["title"]

    def test_second_tick_does_not_rep_push(self) -> None:
        user = UserFactory()
        self._overdue_tx(user)
        _make_sub(user)
        with patch("apps.notifications.services.webpush"):
            tick()
        with patch("apps.notifications.services.webpush") as mock_send:
            result = tick()
        assert result == {"users": 1, "pushed": 0}
        assert mock_send.call_count == 0

    def test_prunes_gone_subscriptions(self) -> None:
        user = UserFactory()
        self._overdue_tx(user)
        sub = _make_sub(user)
        error = WebPushException("gone")
        error.response = SimpleNamespace(status_code=410)
        with patch("apps.notifications.services.webpush", side_effect=error):
            result = tick()
        assert result == {"users": 1, "pushed": 0}
        assert not PushSubscription.objects.filter(pk=sub.pk).exists()

    def test_transient_error_keeps_subscription(self) -> None:
        user = UserFactory()
        self._overdue_tx(user)
        sub = _make_sub(user)
        error = WebPushException("server busy")
        error.response = SimpleNamespace(status_code=503)
        with patch("apps.notifications.services.webpush", side_effect=error):
            result = tick()
        assert result == {"users": 1, "pushed": 0}
        assert PushSubscription.objects.filter(pk=sub.pk).count() == 1

    def test_caps_pushes_per_user(self) -> None:
        user = UserFactory()
        for n in range(5):
            self._overdue_tx(user, concepto=f"Pendiente {n}")
        _make_sub(user)
        with patch("apps.notifications.services.webpush") as mock_send:
            result = tick()
        assert result["pushed"] == 3
        assert mock_send.call_count == 3

    def test_ignores_users_without_subscription(self) -> None:
        """Sin suscripción el tick no lo procesa: la generación in-app sigue
        siendo perezosa (GET /notifications) y no se duplica aquí."""
        user = UserFactory()
        self._overdue_tx(user)
        with patch("apps.notifications.services.webpush") as mock_send:
            result = tick()
        assert result == {"users": 0, "pushed": 0}
        assert mock_send.call_count == 0
        assert Notification.objects.filter(user=user).count() == 0

    def test_lock_prevents_overlapping_cycles(self) -> None:
        user = UserFactory()
        self._overdue_tx(user)
        _make_sub(user)
        cache.set(TICK_LOCK_KEY, 1, timeout=60)
        try:
            with patch("apps.notifications.services.webpush") as mock_send:
                result = tick()
        finally:
            cache.delete(TICK_LOCK_KEY)
        assert result is None
        assert mock_send.call_count == 0


@pytest.mark.django_db
class TestExpenseNudge:
    """Recordatorio diario «¿gastos sin registrar?» (umbral 19:00 locales)."""

    CCS = ZoneInfo("America/Caracas")

    def test_silent_before_threshold_hour(self, settings) -> None:
        settings.NUDGE_LOCAL_HOUR = 19
        user = UserFactory(timezone_name="America/Caracas")
        now_local = datetime(2026, 8, 24, 18, 59, tzinfo=self.CCS)
        assert nudge_candidate(user, now_local) == []

    def test_fires_evening_without_activity(self, settings) -> None:
        settings.NUDGE_LOCAL_HOUR = 19
        user = UserFactory(timezone_name="America/Caracas")
        now_local = datetime(2026, 8, 24, 20, 0, tzinfo=self.CCS)
        items = nudge_candidate(user, now_local)
        assert len(items) == 1
        assert items[0]["kind"] == "expense_nudge"
        assert items[0]["extra"] == {"date": "2026-08-24"}
        assert "gasto" in items[0]["title"].lower()

    def test_suppressed_when_activity_same_local_day(self, settings) -> None:
        settings.NUDGE_LOCAL_HOUR = 19
        user = UserFactory(timezone_name="America/Caracas")
        tx = TransactionFactory(user=user)  # created_at = ahora (UTC)
        local_created = tx.created_at.astimezone(self.CCS)
        # Mismo día local que la transacción, pasada la hora umbral.
        now_local = local_created.replace(hour=20, minute=0, second=0)
        assert nudge_candidate(user, now_local) == []

    def test_one_per_day_via_dedup(self, settings) -> None:
        settings.NUDGE_LOCAL_HOUR = 19
        user = UserFactory(timezone_name="America/Caracas")
        now_local = datetime(2026, 8, 24, 20, 0, tzinfo=self.CCS)
        candidates = nudge_candidate(user, now_local)
        first = _notify_missing(user, candidates)
        second = _notify_missing(user, candidates)
        assert len(first) == 1
        assert second == []
        assert Notification.objects.filter(user=user, kind="expense_nudge").count() == 1

    def test_tick_sends_nudge_in_utc_window(self, settings) -> None:
        settings.NUDGE_LOCAL_HOUR = 19
        user = UserFactory(timezone_name="America/Caracas")
        _make_sub(user)
        # 00:30 UTC del día siguiente son 20:30 del día anterior en Caracas.
        moment = datetime(2026, 8, 25, 0, 30, tzinfo=dt_timezone.utc)
        with patch("apps.notifications.services.webpush") as mock_send:
            result = tick(now=moment)
        assert result is not None and result["users"] == 1
        kinds = [p["kind"] for p in _payloads(mock_send)]
        assert "expense_nudge" in kinds

    def test_activity_in_other_timezone_counts_for_its_own_day(self, settings) -> None:
        settings.NUDGE_LOCAL_HOUR = 19
        user = UserFactory(timezone_name="America/Caracas")
        tx = TransactionFactory(user=user)  # hoy UTC ⇒ hoy Caracas (UTC-4)
        local_created = tx.created_at.astimezone(self.CCS)
        # Tarde (20:00) del día local SIGUIENTE al registro.
        next_evening_local = datetime.combine(
            local_created.date() + timedelta(days=1),
            dt_time(20, 0),
            tzinfo=self.CCS,
        )
        items = nudge_candidate(user, next_evening_local)
        # La actividad fue del día local anterior ⇒ el nudge de HOY procede.
        assert len(items) == 1
        assert items[0]["extra"] == {
            "date": (local_created.date() + timedelta(days=1)).isoformat()
        }

    def test_invalid_timezone_falls_back(self) -> None:
        user = UserFactory(timezone_name="Marte/Olympus")
        aware = datetime.now(dt_timezone.utc)
        items = nudge_candidate(user, aware.replace(hour=20))
        assert isinstance(items, list)
