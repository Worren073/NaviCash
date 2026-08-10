"""tests — Notificaciones: generación, deduplicación y estado leída."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from apps.notifications.models import Notification
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
        with django_assert_num_queries(5):
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
