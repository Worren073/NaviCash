"""Tests del flujo de eliminación de cuenta (derecho al olvido, art. 17).

Cubre:
- ``POST /api/auth/delete-account``: contraseña obligatoria (+lockout),
  agendado con gracia, revocación de sesiones, correo y notificación.
- ``POST /api/auth/cancel-account-deletion``: cancela solo si hay pendiente.
- ``purge_due_accounts``: borra cuenta vencida con TODOS sus datos
  (incluidos BalanceAuditLog), libera el email y no toca cuentas sanas.
- Disparador perezoso diario (``maybe_purge_daily``): lock de un run/día y
  exclusión del usuario que dispara.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core import mail
from django.core.cache import cache
from django.utils import timezone
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.accounts.services import PURGE_LOCK_KEY, maybe_purge_daily, purge_due_accounts
from apps.notifications.models import Notification
from apps.wallets.models import BalanceAuditLog, Wallet
from factories import UserFactory, WalletFactory

URL_DELETE = "/api/auth/delete-account"
URL_CANCEL = "/api/auth/cancel-account-deletion"


# ---------------------------------------------------------------------------
# POST /api/auth/delete-account
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestDeleteAccountEndpoint:
    """Solicitud de eliminación: identidad + efectos laterales."""

    def test_requires_authentication(self) -> None:
        resp = APIClient().post(URL_DELETE, {"password": "test-password-123"})
        assert resp.status_code == 401

    def test_wrong_password_rejected_and_counted(self, api_client) -> None:
        resp = api_client.post(URL_DELETE, {"password": "incorrecta"})
        assert resp.status_code == 400
        api_client.user.refresh_from_db()
        assert api_client.user.deletion_scheduled_at is None
        # Contador de lockout incrementado (clave separada del login).
        assert cache.get(f"delete_failed:{api_client.user.pk}") == 1

    def test_lockout_after_max_failures(self, api_client) -> None:
        pk = api_client.user.pk
        cache.set(f"delete_failed:{pk}", 5, timeout=900)
        resp = api_client.post(URL_DELETE, {"password": "lo-que-sea"})
        assert resp.status_code == 429

    def test_success_schedules_grace_and_revokes_sessions(self, api_client) -> None:
        user = api_client.user
        OutstandingToken.objects.create(
            user=user,
            jti="jti-sesion-vieja",
            token="token-viejo",
            expires_at=timezone.now() + timedelta(days=1),
        )
        before = timezone.now()

        resp = api_client.post(URL_DELETE, {"password": api_client.user_password})

        assert resp.status_code == 200
        user.refresh_from_db()
        expected = before + timedelta(days=15)
        assert user.deletion_scheduled_at is not None
        delta = abs((user.deletion_scheduled_at - expected).total_seconds())
        assert delta < 120, "La gracia debe ser ~15 días desde la solicitud"
        # DRF serializa con sufijo "Z"; el isoformat de Python usa "+00:00".
        assert resp.data["deletion_scheduled_at"] == (
            user.deletion_scheduled_at.isoformat().replace("+00:00", "Z")
        )
        # Sesiones revocadas y cookie de refresh limpiada.
        assert not OutstandingToken.objects.filter(user=user).exists()
        assert "refresh_token" in resp.cookies

    def test_success_sends_email_and_notification(self, api_client) -> None:
        resp = api_client.post(URL_DELETE, {"password": api_client.user_password})
        assert resp.status_code == 200
        assert len(mail.outbox) == 1
        assert api_client.user.email in mail.outbox[0].to
        assert "15 días" in mail.outbox[0].body
        assert Notification.objects.filter(
            user=api_client.user,
            kind="system",
            extra={"scope": "account_deletion", "action": "scheduled"},
        ).exists()

    def test_me_exposes_deletion_date(self, api_client) -> None:
        api_client.post(URL_DELETE, {"password": api_client.user_password})
        me = api_client.get("/api/auth/me")
        assert me.status_code == 200
        assert me.data["deletion_scheduled_at"] is not None


# ---------------------------------------------------------------------------
# POST /api/auth/cancel-account-deletion
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestCancelAccountDeletionEndpoint:
    """Cancelación dentro del período de gracia."""

    def test_cancel_without_pending_fails(self, api_client) -> None:
        resp = api_client.post(URL_CANCEL)
        assert resp.status_code == 400

    def test_cancel_clears_schedule(self, api_client) -> None:
        api_client.post(URL_DELETE, {"password": api_client.user_password})
        resp = api_client.post(URL_CANCEL)
        assert resp.status_code == 200
        api_client.user.refresh_from_db()
        assert api_client.user.deletion_scheduled_at is None
        assert resp.data["user"]["deletion_scheduled_at"] is None


# ---------------------------------------------------------------------------
# Purga definitiva
# ---------------------------------------------------------------------------


def _seed_data(user):
    """Billetera + log de auditoría para verificar el borrado en cascada."""
    wallet = WalletFactory(user=user, saldo=Decimal("100.00"))
    BalanceAuditLog.objects.create(
        wallet=wallet, delta=Decimal("10.00"), balance_after=Decimal("110.00"),
        reason="ajuste_manual", user=user,
    )
    return wallet


@pytest.mark.django_db
class TestPurgeDueAccounts:
    """Borrado definitivo cuando la gracia venció."""

    def test_due_user_deleted_with_all_data(self) -> None:
        victim = UserFactory(email="victim@example.com")
        survivor = UserFactory()
        wallet_victim = _seed_data(victim)
        wallet_survivor = _seed_data(survivor)

        victim.deletion_scheduled_at = timezone.now() - timedelta(minutes=5)
        victim.save(update_fields=["deletion_scheduled_at"])

        deleted = purge_due_accounts()

        assert deleted == 1
        assert not User.objects.filter(pk=victim.pk).exists()
        assert User.objects.filter(pk=survivor.pk).exists()
        # Cascade + audit logs borrados explícitamente.
        assert not Wallet.objects.filter(pk=wallet_victim.pk).exists()
        assert not BalanceAuditLog.objects.filter(wallet=wallet_victim).exists()
        # El usuario sano conserva todo, incluidos sus logs.
        assert Wallet.objects.filter(pk=wallet_survivor.pk).exists()
        assert BalanceAuditLog.objects.filter(user=survivor).count() == 1

    def test_future_scheduled_user_not_deleted(self) -> None:
        pending = UserFactory()
        pending.deletion_scheduled_at = timezone.now() + timedelta(days=3)
        pending.save(update_fields=["deletion_scheduled_at"])
        assert purge_due_accounts() == 0
        assert User.objects.filter(pk=pending.pk).exists()

    def test_email_is_freed_after_purge(self) -> None:
        victim = UserFactory(email="liberado@example.com")
        victim.deletion_scheduled_at = timezone.now() - timedelta(days=1)
        victim.save(update_fields=["deletion_scheduled_at"])
        purge_due_accounts()
        # El email queda reutilizable para un nuevo registro.
        reborn = User.objects.create_user(
            email="liberado@example.com", password="nueva-pass-123"
        )
        assert reborn.email == "liberado@example.com"


@pytest.mark.django_db
class TestLazyPurgeTrigger:
    """Disparador perezoso desde MeView.get."""

    def test_me_view_triggers_daily_purge_excepting_caller(self, api_client) -> None:
        stranger = UserFactory()
        stranger.deletion_scheduled_at = timezone.now() - timedelta(hours=1)
        stranger.save(update_fields=["deletion_scheduled_at"])

        resp = api_client.get("/api/auth/me")
        assert resp.status_code == 200
        assert not User.objects.filter(pk=stranger.pk).exists()
        # Lock diario activo tras la corrida.
        assert cache.get(PURGE_LOCK_KEY) == timezone.localdate().isoformat()

    def test_runs_only_once_per_day(self) -> None:
        assert maybe_purge_daily() == 0  # primera corrida (sin vencidos)
        assert cache.get(PURGE_LOCK_KEY) is not None
        assert maybe_purge_daily() is None  # misma fecha → no vuelve a correr
