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
            user=api_client.user, fecha_vencimiento=date.today() - timedelta(days=1)
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
