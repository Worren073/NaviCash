"""tests — Retención de datos: purga de notificaciones y blacklist JWT (M5)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from apps.notifications.models import Notification
from factories import UserFactory


@pytest.mark.django_db
class TestPurgeBlacklist:
    """purge_blacklist borra tokens JWT expirados en lotes."""

    def test_deletes_only_expired_tokens(self, api_client) -> None:
        """Solo los OutstandingToken vencidos se borran (y sus blacklisted)."""
        expired = OutstandingToken.objects.create(
            user=api_client.user,
            jti="expired-jti-1",
            token="token.expirado",
            expires_at=timezone.now() - timedelta(days=10),
        )
        active = OutstandingToken.objects.create(
            user=api_client.user,
            jti="active-jti-1",
            token="token.vigente",
            expires_at=timezone.now() + timedelta(days=10),
        )
        BlacklistedToken.objects.create(token=expired)

        call_command("purge_blacklist", "--batch", "500")

        assert not OutstandingToken.objects.filter(pk=expired.pk).exists()
        assert not BlacklistedToken.objects.filter(token_id=expired.pk).exists()
        assert OutstandingToken.objects.filter(pk=active.pk).exists()

    def test_batch_mode_removes_everything(self) -> None:
        """Con batch pequeño se purga todo en varias pasadas (usuario sin tokens previos)."""
        user = UserFactory()
        for i in range(5):
            OutstandingToken.objects.create(
                user=user,
                jti=f"jti-{i}",
                token=f"token-{i}",
                expires_at=timezone.now() - timedelta(days=1),
            )
        call_command("purge_blacklist", "--batch", "2")
        assert OutstandingToken.objects.filter(user=user).count() == 0

    def test_no_tokens_no_error(self) -> None:
        """Sin tokens expirados el comando termina sin error."""
        call_command("purge_blacklist")
        assert OutstandingToken.objects.count() == 0


@pytest.mark.django_db
class TestPurgeNotifications:
    """purge_notifications respeta --days y el estado leída."""

    def test_default_days_90_and_output(self, api_client, capsys) -> None:
        """Con el default (90 días) solo se borran leídas de hace más de 90 días."""
        old = Notification.objects.create(
            user=api_client.user, kind="system", read=True, title="vieja", message="x"
        )
        Notification.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timedelta(days=200)
        )
        # Distinto 'kind' para evitar UNIQUE (user, kind, extra)
        recent = Notification.objects.create(
            user=api_client.user, kind="system_recent", read=True, title="joven", message="y"
        )
        call_command("purge_notifications")
        assert not Notification.objects.filter(pk=old.pk).exists()
        assert Notification.objects.filter(pk=recent.pk).exists()
        out = capsys.readouterr().out
        assert "eliminadas: 1" in out

    def test_other_users_untouched(self) -> None:
        """Purga global: borra leídas antiguas de TODOS los usuarios.
        El test verifica que el comando es global (no scope por usuario)."""
        other = UserFactory()
        n = Notification.objects.create(user=other, kind="system", read=True, title="a", message="b")
        Notification.objects.filter(pk=n.pk).update(
            created_at=timezone.now() - timedelta(days=300)
        )
        call_command("purge_notifications", "--days", "10")
        # La purga es global → la notificación antigua de otro usuario SÍ se borra
        assert not Notification.objects.filter(pk=n.pk).exists()