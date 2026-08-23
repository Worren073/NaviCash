"""tests — Asistente Navi: contexto, fallback determinista, auth y rate limit."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from apps.assistant.context import build_context
from apps.assistant.intent_rules import answer_deterministic
from apps.assistant.models import ChatMessage
from apps.rates.models import ExchangeRate
from apps.subscriptions.models import Subscription
from factories import (
    GoalContributionFactory,
    SavingsGoalFactory,
    TransactionFactory,
    UserFactory,
    WalletFactory,
)
from django.utils import timezone


def _seed_rate() -> None:
    """Siembra una tasa oficial para conversiones (100 VES/USD)."""
    if not ExchangeRate.objects.filter(source="oficial").exists():
        ExchangeRate.objects.create(
            source="oficial",
            currency="VES",
            promedio=Decimal("100.00"),
            rate_date=timezone.now(),
        )


@pytest.mark.django_db
class TestBuildContext:
    """build_context regresa un resumen JSON-friendly del usuario."""

    def test_context_is_flat_and_scoped(self, api_client) -> None:
        """El contexto solo contiene datos del propio usuario y es JSONizable."""
        _seed_rate()
        other = UserFactory()
        WalletFactory(user=other, saldo=Decimal("999.00"))

        WalletFactory(user=api_client.user, saldo=Decimal("50.00"), currency="USD")
        context = build_context(api_client.user)

        assert context["total_balance_usd"] == "50.00"
        assert context["base_currency"] == "USD"
        assert context["rate"] is not None
        assert context["euro_rate"] is not None
        # No expone emails/credenciales en ningún nivel.
        assert "@" not in str(context).lower()

    def test_includes_goals_and_contributions(self, api_client) -> None:
        """Metas con avance calculado a partir de los aportes."""
        goal = SavingsGoalFactory(
            user=api_client.user, name="Viaje", target_amount=Decimal("1000.00")
        )
        GoalContributionFactory(
            user=api_client.user,
            goal=goal,
            amount=Decimal("250.00"),
            amount_goal_currency=Decimal("250.00"),
        )
        context = build_context(api_client.user)
        assert context["goals"][0]["name"] == "Viaje"
        assert Decimal(context["goals"][0]["total_contributed"]) == Decimal("250.00")

    def test_includes_subscriptions_and_fin_month(self, api_client) -> None:
        """Mensualidades y flujo del mes corriente."""
        Subscription.objects.create(
            user=api_client.user,
            name="Netflix",
            start_date=date.today() - timedelta(days=10),
            end_date=date.today() + timedelta(days=20),
        )
        _seed_rate()
        # Un pago pagado este mes (USD congelado) computa en el flujo.
        TransactionFactory(
            user=api_client.user,
            tipo="pago",
            estado="pagado",
            monto=Decimal("40.00"),
            moneda="USD",
            monto_usd=Decimal("40.00"),
            fecha=date.today(),
            fecha_pagado=None,
        )
        context = build_context(api_client.user)
        assert context["subscriptions"][0]["name"] == "Netflix"
        assert context["subscriptions"][0]["status"] == "activa"
        assert context["fin_month"]["expenses"] == "40.00"


@pytest.mark.django_db
class TestDeterministicFallback:
    """Fallback determinista responde intents comunes sin red."""

    def _with_balance(self, user) -> dict:
        WalletFactory(user=user, saldo=Decimal("100.00"), currency="USD")
        return build_context(user)

    def test_saldo_intent(self, api_client) -> None:
        """«¿Cuánto tengo?» devuelve el saldo total."""
        context = self._with_balance(api_client.user)
        resp = answer_deterministic(context, "cuanto tengo?")
        assert "100.00" in resp
        assert "USD" in resp

    def test_pay_intent_with_data(self, api_client) -> None:
        """«¿Qué debo?» con un pago vencido devuelve el monto."""
        _seed_rate()
        TransactionFactory(
            user=api_client.user,
            tipo="pago",
            monto=Decimal("20.00"),
            moneda="USD",
            monto_usd=Decimal("20.00"),
            fecha=date.today() - timedelta(days=5),
            fecha_vencimiento=date.today() - timedelta(days=1),
        )
        context = build_context(api_client.user)
        resp = answer_deterministic(context, "cuanto debo?")
        assert "20.00" in resp

    def test_pay_intent_empty(self, api_client) -> None:
        """Sin pagos vencidos, responde tranquilizador."""
        context = build_context(api_client.user)
        resp = answer_deterministic(context, "debo algo?")
        assert "No tienes pagos vencidos" in resp

    def test_goals_intent(self, api_client) -> None:
        """Intento de ahorro lista metas y progreso."""
        goal = SavingsGoalFactory(
            user=api_client.user, name="Emergencia", target_amount=Decimal("500.00")
        )
        GoalContributionFactory(
            user=api_client.user,
            goal=goal,
            amount=Decimal("100.00"),
            amount_goal_currency=Decimal("100.00"),
        )
        resp = answer_deterministic(build_context(api_client.user), "como vamos con mis metas")
        assert "Emergencia" in resp
        assert "20.00%" in resp  # 100/500

    def test_subscriptions_intent(self, api_client) -> None:
        """Intento de mensualidades lista las vigentes."""
        Subscription.objects.create(
            user=api_client.user,
            name="Spotify",
            start_date=date.today() - timedelta(days=5),
            end_date=date.today() + timedelta(days=25),
        )
        resp = answer_deterministic(build_context(api_client.user), "que mensualidades tengo?")
        assert "Spotify" in resp
        assert "activa" in resp

    def test_afford_intent(self, api_client) -> None:
        """«¿Me puedo permitir X?» compara el gasto con el flujo del mes."""
        context = build_context(api_client.user)
        resp = answer_deterministic(context, "me puedo gastar 10 dolares")
        assert "10.00" in resp

    def test_unknown_intent_generic(self, api_client) -> None:
        """Viñeta por defecto sugiere intents disponibles."""
        resp = answer_deterministic(build_context(api_client.user), "adasdsa zxc")
        assert "¿Cuánto tengo?" in resp


@pytest.mark.django_db
class TestChatEndpoint:
    """POST /api/assistant/messages: auth, validación, respuesta y rate."""

    URL = "/api/assistant/messages"

    def test_requires_authentication(self) -> None:
        """Sin token devuelve 401."""
        from rest_framework.test import APIClient

        resp = APIClient().post(self.URL, {"message": "hola"}, format="json")
        assert resp.status_code == 401

    def test_invalid_message_rejected(self, api_client) -> None:
        """Mensaje vacío o inexistente devuelve 400."""
        resp = api_client.post(self.URL, {}, format="json")
        assert resp.status_code == 400
        assert "message" in resp.data["errors"]

    def test_empty_message_rejected(self, api_client) -> None:
        """Mensaje de solo espacios devuelve 400."""
        resp = api_client.post(self.URL, {"message": "   "}, format="json")
        assert resp.status_code == 400

    def test_returns_reply_and_persists(self, api_client) -> None:
        """Un mensaje válido responde 200 y guarda el turno en la sesión."""
        resp = api_client.post(
            self.URL, {"message": "cuánto tengo?"}, format="json"
        )
        assert resp.status_code == 200
        assert "text" in resp.data
        assert "session_id" in resp.data

        session_id = resp.data["session_id"]
        assert ChatMessage.objects.filter(user=api_client.user, session_id=session_id).count() == 2

    def test_session_id_reused(self, api_client) -> None:
        """El mismo session_id agrupa los turnos en una sola conversación."""
        first = api_client.post(self.URL, {"message": "hola"}, format="json")
        second = api_client.post(
            self.URL,
            {"message": "cuánto tengo?", "session_id": first.data["session_id"]},
            format="json",
        )
        assert second.data["session_id"] == first.data["session_id"]

    def test_user_sees_only_own_history(self, api_client, auth_client_factory) -> None:
        """El historial por sesión solo muestra mensajes del propio usuario."""
        me = api_client
        other = auth_client_factory()
        resp_me = me.post(self.URL, {"message": "hola"}, format="json")
        session = resp_me.data["session_id"]

        # El otro usuario no puede leer esa sesión (no tiene mensajes).
        hist = other.get("/api/assistant/messages/history", {"session_id": session})
        assert hist.status_code == 200
        assert hist.data == []

        # El propietario sí.
        hist_me = me.get("/api/assistant/messages/history", {"session_id": session})
        assert hist_me.status_code == 200
        assert len(hist_me.data) == 2


@pytest.mark.django_db
class TestChatRateLimit:
    """El scope 'assistant' aplica límite de peticiones por usuario."""

    URL = "/api/assistant/messages"

    def test_exceeds_limit(self, api_client, monkeypatch) -> None:
        """Después del límite, el endpoint devuelve 429.

        Se patchea la vista con un throttle de rate fija: ``override_settings``
        de ``DEFAULT_THROTTLE_RATES`` NO surte efecto porque DRF cachea
        ``api_settings`` al primer acceso en el proceso de tests.
        """
        from rest_framework.throttling import ScopedRateThrottle

        class FastAssistantThrottle(ScopedRateThrottle):
            """Throttle de prueba: 3 peticiones por minuto en el scope."""

            scope = "assistant"
            THROTTLE_RATES = {"assistant": "3/minute"}

        from apps.assistant import views as assistant_views

        monkeypatch.setattr(assistant_views.ChatView, "throttle_classes", [FastAssistantThrottle])

        statuses = []
        for _ in range(4):
            resp = api_client.post(self.URL, {"message": "hola"}, format="json")
            statuses.append(resp.status_code)
        assert 429 in statuses