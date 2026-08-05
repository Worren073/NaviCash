"""tests — Flujo de cuentas: registro, verificación, login, refresh, logout, me."""

from __future__ import annotations

import pytest
from django.core import mail

from apps.accounts.models import User
from factories import EmailVerificationFactory, UserFactory


@pytest.mark.django_db
class TestRegister:
    """Endpoints POST /api/auth/register."""

    URL = "/api/auth/register"

    def test_creates_inactive_user(self, api_client) -> None:
        """El registro crea el usuario inactivo y devuelve 201."""
        from django.contrib.auth import get_user_model

        User = get_user_model()  # noqa: F811
        resp = api_client.post(
            self.URL,
            {"email": "nuevo@example.com", "password": "clave-segura-123"},
        )
        assert resp.status_code == 201
        assert User.objects.filter(email="nuevo@example.com", is_active=False).exists()

    def test_returns_debug_token_when_debug(self, api_client) -> None:
        """En DEBUG el registro devuelve el token (para pruebas locales)."""
        resp = api_client.post(
            self.URL,
            {"email": "debug@example.com", "password": "clave-segura-123"},
        )
        assert resp.status_code == 201
        assert "debug_token" in resp.data

    def test_sends_verification_email(self, api_client) -> None:
        """Se envía un correo de verificación al registrarse."""
        resp = api_client.post(
            self.URL,
            {"email": "correo@example.com", "password": "clave-segura-123"},
        )
        assert resp.status_code == 201
        assert len(mail.outbox) == 1
        assert "correo@example.com" in mail.outbox[0].to

    def test_duplicate_email_rejected(self, api_client) -> None:
        """No se permite registrar dos veces el mismo email."""
        UserFactory(email="dup@example.com")
        resp = api_client.post(
            self.URL,
            {"email": "DUP@example.com", "password": "clave-segura-123"},
        )
        assert resp.status_code == 400
        assert "email" in resp.data["errors"]


@pytest.mark.django_db
class TestVerifyEmail:
    """Endpoint POST /api/auth/verify-email."""

    URL = "/api/auth/verify-email"

    def test_activates_account_with_valid_token(self, api_client) -> None:
        """Un token válido activa la cuenta."""
        user = UserFactory(email="activable@example.com", is_active=False)
        verification = EmailVerificationFactory(user=user)
        resp = api_client.post(self.URL, {"token": verification.token})
        assert resp.status_code == 200
        user.refresh_from_db()
        assert user.is_active is True

    def test_rejects_used_token(self, api_client) -> None:
        """Un token ya usado no puede reutilizarse."""
        user = UserFactory(email="usado@example.com", is_active=False)
        verification = EmailVerificationFactory(user=user, used=True)
        resp = api_client.post(self.URL, {"token": verification.token})
        assert resp.status_code == 400

    def test_rejects_unknown_token(self, api_client) -> None:
        """Un token inexistente da error 400."""
        resp = api_client.post(self.URL, {"token": "token-inexistente"})
        assert resp.status_code == 400


@pytest.mark.django_db
class TestAuthFlow:
    """Login, refresh, logout y perfil."""

    LOGIN_URL = "/api/auth/login"
    ME_URL = "/api/auth/me"

    def _login(self, client, email: str, password: str):
        """Helper de login devolviendo la respuesta."""
        return client.post(self.LOGIN_URL, {"email": email, "password": password})

    def test_login_success_sets_cookie_and_access(self, api_client) -> None:
        """Login exitoso: access en body y refresh en cookie httpOnly."""
        user = UserFactory(email="cajero@example.com")
        resp = self._login(api_client, "cajero@example.com", "test-password-123")
        assert resp.status_code == 200
        assert resp.data["access"]
        assert resp.cookies["refresh_token"]["httponly"] is True

    def test_login_rejects_inactive_account(self, api_client) -> None:
        """Cuenta sin verificar no puede iniciar sesión (código not_verified)."""
        UserFactory(email="inactivo@example.com", is_active=False)
        resp = self._login(api_client, "inactivo@example.com", "test-password-123")
        assert resp.status_code == 401

    def test_login_wrong_password(self, api_client) -> None:
        """Contraseña incorrecta devuelve 401."""
        UserFactory(email="clave@example.com")
        resp = self._login(api_client, "clave@example.com", "password-incorrecta")
        assert resp.status_code == 401

    def test_me_returns_profile(self, api_client) -> None:
        """GET /api/auth/me devuelve el perfil del token."""
        resp = api_client.get(self.ME_URL)
        assert resp.status_code == 200
        assert resp.data["email"]

    def test_me_updates_profile(self, api_client) -> None:
        """PATCH /api/auth/me actualiza el perfil (RF-05)."""
        resp = api_client.patch(
            self.ME_URL, {"name": "Ana Actualizada", "reminder_days": 5}
        )
        assert resp.status_code == 200
        assert resp.data["name"] == "Ana Actualizada"
        assert resp.data["reminder_days"] == 5

    def test_me_requires_auth(self) -> None:
        """Sin token, /me responde 401."""
        from rest_framework.test import APIClient

        resp = APIClient().get(self.ME_URL)
        assert resp.status_code in (401, 403)