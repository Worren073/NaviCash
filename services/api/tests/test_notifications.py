"""tests — Notificaciones: generación, deduplicación, ámbito y retención."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest

from apps.business.services import create_business
from apps.notifications.models import Notification, PushSubscription
from apps.notifications.services import deliver_pushes
from factories import GoalContributionFactory, SavingsGoalFactory, TransactionFactory, UserFactory


@pytest.mark.django_db
class TestNotifications:
    """Endpoints GET/POST /api/notifications."""

    URL = "/api/notifications"

    def test_generates_due_soon(self, api_client) -> None:
        """Una operación con vencimiento próximo genera 'due_soon'."""
        TransactionFactory(
            user=api_client.user, fecha_vencimiento=date.today() + timedelta(days=2)
        )
        resp = api_client.get(self.URL)
        assert resp.status_code == 200
        kinds = {n["kind"] for n in resp.data["results"]}
        assert "due_soon" in kinds
        assert resp.data["unread_count"] >= 1

    def test_generates_overdue(self, api_client) -> None:
        """Una operación vencida y sin pagar genera 'overdue'."""
        TransactionFactory(
            user=api_client.user,
            fecha=date.today() - timedelta(days=5),
            fecha_vencimiento=date.today() - timedelta(days=1),
        )
        resp = api_client.get(self.URL)
        kinds = {n["kind"] for n in resp.data["results"]}
        assert "overdue" in kinds

    def test_no_duplicates_on_refresh(self, api_client) -> None:
        """Consultar varias veces no duplica la misma alerta sin leer."""
        TransactionFactory(
            user=api_client.user, fecha_vencimiento=date.today() + timedelta(days=1)
        )
        api_client.get(self.URL)
        api_client.get(self.URL)
        count = Notification.objects.filter(user=api_client.user, kind="due_soon").count()
        assert count == 1

    def test_goal_reached_notification(self, api_client) -> None:
        """Meta completada genera 'goal_reached'."""
        goal = SavingsGoalFactory(user=api_client.user, target_amount="100.00")
        GoalContributionFactory(
            user=api_client.user, goal=goal, amount="100.00", amount_goal_currency="100.00"
        )
        resp = api_client.get(self.URL)
        kinds = {n["kind"] for n in resp.data["results"]}
        assert "goal_reached" in kinds

    def test_mark_read(self, api_client) -> None:
        """POST /notifications/<id>/read marca una como leída."""
        TransactionFactory(
            user=api_client.user, fecha_vencimiento=date.today() + timedelta(days=1)
        )
        api_client.get(self.URL)
        notif = Notification.objects.get(user=api_client.user, kind="due_soon")
        resp = api_client.post(f"{self.URL}/{notif.id}/read")
        assert resp.status_code == 200
        notif.refresh_from_db()
        assert notif.read is True

    def test_read_all(self, api_client) -> None:
        """POST /notifications/read-all marca todo como leído."""
        TransactionFactory(
            user=api_client.user, fecha_vencimiento=date.today() + timedelta(days=1)
        )
        api_client.get(self.URL)
        resp = api_client.post(f"{self.URL}/read-all")
        assert resp.status_code == 200
        assert not Notification.objects.filter(user=api_client.user, read=False).exists()

    def test_read_all_does_not_regenerate(self, api_client) -> None:
        """Marcar como leído no vuelve a crear la misma alerta en el siguiente GET."""
        TransactionFactory(
            user=api_client.user, fecha_vencimiento=date.today() + timedelta(days=1)
        )
        api_client.get(self.URL)
        total_before = Notification.objects.filter(user=api_client.user).count()
        api_client.post(f"{self.URL}/read-all")
        api_client.get(self.URL)
        assert Notification.objects.filter(user=api_client.user).count() == total_before
        assert not Notification.objects.filter(user=api_client.user, read=False).exists()

    def test_scoped_to_user(self, api_client) -> None:
        """Las alertas de otros usuarios no se ven ni se cuentan."""
        other = UserFactory()
        TransactionFactory(
            user=other, fecha_vencimiento=date.today() + timedelta(days=1)
        )
        resp = api_client.get(self.URL)
        assert resp.status_code == 200
        assert resp.data["unread_count"] == 0

    def test_bulk_creates_missing_in_single_pass(self, api_client, django_assert_num_queries) -> None:
        """La regeneración crea las faltantes en UNA pasada (A8), sin
        exists()/create() por fila."""
        from apps.notifications.services import refresh_notifications

        for _ in range(3):
            TransactionFactory(
                user=api_client.user,
                fecha=date.today() - timedelta(days=5),
                fecha_vencimiento=date.today() - timedelta(days=1),
            )
        with django_assert_num_queries(6):
            refresh_notifications(api_client.user)
        assert (
            Notification.objects.filter(user=api_client.user, kind="overdue").count()
            == 3
        )

    def test_purge_notifications_command(self, api_client) -> None:
        """purge_notifications borra solo leídas antiguas (M5)."""
        from datetime import timedelta

        from django.core.management import call_command
        from django.utils import timezone

        def _old_read(kind: str, ref: str) -> Notification:
            n = Notification.objects.create(
                user=api_client.user, kind=kind, read=True, title=ref, message="a",
                extra={"ref": ref},
            )
            Notification.objects.filter(pk=n.pk).update(
                created_at=timezone.now() - timedelta(days=120)
            )
            return n

        _old_read(kind="system", ref="vieja-1")
        _old_read(kind="system", ref="vieja-2")
        # Reciente leída: NO se borra.
        Notification.objects.create(
            user=api_client.user, kind="system", read=True, title="reciente",
            message="c", extra={"ref": "reciente"},
        )
        # Antigua NO leída: NO se borra.
        old_unread = Notification.objects.create(
            user=api_client.user, kind="system", read=False, title="sin leer",
            message="d", extra={"ref": "sin-leer"},
        )
        Notification.objects.filter(pk=old_unread.pk).update(
            created_at=timezone.now() - timedelta(days=120)
        )

        call_command("purge_notifications", "--days", "90")
        remaining = list(
            Notification.objects.filter(user=api_client.user).values_list("extra__ref", flat=True)
        )
        assert sorted(remaining) == ["reciente", "sin-leer"]

    def test_business_scope_isolated(self, api_client) -> None:
        """Las notificaciones de negocio se consultan por scope=business y no
        aparecen en el scope personal."""
        business = create_business(
            api_client.user, name="Cafetería", currency="USD", initial_capital=Decimal("0")
        )
        TransactionFactory(
            user=api_client.user,
            wallet=business.wallet,
            fecha_vencimiento=date.today() + timedelta(days=1),
        )
        # Negocio: debe aparecer.
        resp = api_client.get(f"{self.URL}?scope=business")
        assert resp.status_code == 200
        assert resp.data["unread_count"] == 1
        assert len(resp.data["results"]) == 1
        assert resp.data["results"][0]["scope"] == "business"
        assert resp.data["results"][0]["kind"] == "due_soon"
        # Personal: no debe aparecer.
        resp_personal = api_client.get(self.URL)
        assert resp_personal.data["unread_count"] == 0
        assert resp_personal.data["results"] == []

    def test_read_all_scoped(self, api_client) -> None:
        """read-all solo marca como leídas las del scope indicado."""
        TransactionFactory(
            user=api_client.user, fecha_vencimiento=date.today() + timedelta(days=1)
        )
        business = create_business(
            api_client.user, name="Cafetería", currency="USD", initial_capital=Decimal("0")
        )
        TransactionFactory(
            user=api_client.user,
            wallet=business.wallet,
            fecha_vencimiento=date.today() + timedelta(days=1),
        )
        api_client.get(self.URL)
        api_client.get(f"{self.URL}?scope=business")

        api_client.post(f"{self.URL}/read-all?scope=business")
        assert not Notification.objects.filter(
            user=api_client.user, scope="business", read=False
        ).exists()
        assert Notification.objects.filter(
            user=api_client.user, scope="personal", read=False
        ).exists()

    def test_tray_retention_six(self, api_client) -> None:
        """La bandeja retiene máximo 6 notificaciones no leídas por scope."""
        for days in range(7):
            TransactionFactory(
                user=api_client.user,
                fecha_vencimiento=date.today() + timedelta(days=1),
                concepto=f"Op {days}",
            )
        resp = api_client.get(self.URL)
        assert resp.status_code == 200
        assert len(resp.data["results"]) == 6
        assert resp.data["unread_count"] == 6
        assert Notification.objects.filter(
            user=api_client.user, scope="personal", read=False
        ).count() == 6

    def test_push_payload_scope_and_url(self, api_client) -> None:
        """El payload de push incluye scope y url según el ámbito."""
        PushSubscription.objects.create(
            user=api_client.user,
            endpoint="https://example.com/push/1",
            p256dh="x" * 80,
            auth="y" * 40,
        )
        personal = Notification.objects.create(
            user=api_client.user,
            kind="due_soon",
            scope="personal",
            title="Personal",
            message="m",
            extra={"transaction_id": "1"},
        )
        business = Notification.objects.create(
            user=api_client.user,
            kind="overdue",
            scope="business",
            title="Negocio",
            message="m",
            extra={"transaction_id": "2"},
        )
        payloads: list[dict] = []

        def fake_send(_sub, payload: dict) -> bool:
            payloads.append(payload)
            return True

        with patch("apps.notifications.services.send_web_push", fake_send):
            deliver_pushes(api_client.user, [personal, business])

        assert len(payloads) == 2
        by_scope = {p["scope"]: p["url"] for p in payloads}
        assert by_scope["personal"] == "/"
        assert by_scope["business"] == "/business"
