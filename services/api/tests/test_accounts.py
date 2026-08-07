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

    def _payload(self, **overrides) -> dict:
        """Payload mínimo válido de registro."""
        payload = {
            "email": "nuevo@example.com",
            "password": "clave-segura-123",
            "first_name": "Ana",
            "last_name": "Pérez",
            "phone": "+58 424 123 4567",
            "accepted_terms": True,
        }
        payload.update(overrides)
        return payload

    def test_creates_inactive_user(self, api_client) -> None:
        """El registro crea el usuario inactivo y devuelve 201."""
        from django.contrib.auth import get_user_model

        User = get_user_model()  # noqa: F811
        resp = api_client.post(self.URL, self._payload(email="nuevo@example.com"))
        assert resp.status_code == 201
        user = User.objects.get(email="nuevo@example.com")
        assert user.is_active is False
        assert user.first_name == "Ana"
        assert user.last_name == "Pérez"
        assert user.phone == "+58 424 123 4567"
        assert user.accepted_terms_version

    def test_returns_debug_token_when_debug(self, api_client) -> None:
        """En DEBUG el registro devuelve el token (para pruebas locales)."""
        resp = api_client.post(self.URL, self._payload(email="debug@example.com"))
        assert resp.status_code == 201
        assert "debug_token" in resp.data

    def test_sends_verification_email(self, api_client) -> None:
        """Se envía un correo de verificación al registrarse."""
        resp = api_client.post(self.URL, self._payload(email="correo@example.com"))
        assert resp.status_code == 201
        assert len(mail.outbox) == 1
        assert "correo@example.com" in mail.outbox[0].to

    def test_duplicate_email_rejected(self, api_client) -> None:
        """No se permite registrar dos veces el mismo email."""
        UserFactory(email="dup@example.com")
        resp = api_client.post(
            self.URL, self._payload(email="DUP@example.com")
        )
        assert resp.status_code == 400
        assert "email" in resp.data["errors"]

    def test_terms_required(self, api_client) -> None:
        """Sin aceptar los términos el registro se rechaza."""
        resp = api_client.post(self.URL, self._payload(accepted_terms=False))
        assert resp.status_code == 400
        assert "accepted_terms" in resp.data["errors"]

    def test_weak_password_rejected(self, api_client) -> None:
        """Contraseña sin número o demasiado corta se rechaza."""
        resp = api_client.post(self.URL, self._payload(password="sololetras"))
        assert resp.status_code == 400
        assert "password" in resp.data["errors"]

    def test_invalid_phone_rejected(self, api_client) -> None:
        """Teléfono con formato raro se rechaza."""
        resp = api_client.post(self.URL, self._payload(phone="abc"))
        assert resp.status_code == 400
        assert "phone" in resp.data["errors"]


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
            self.ME_URL,
            {"first_name": "Ana", "last_name": "Actualizada", "reminder_days": 5},
        )
        assert resp.status_code == 200
        assert resp.data["first_name"] == "Ana"
        assert resp.data["last_name"] == "Actualizada"
        assert resp.data["name"] == "Ana Actualizada"
        assert resp.data["reminder_days"] == 5

    def test_me_requires_auth(self) -> None:
        """Sin token, /me responde 401."""
        from rest_framework.test import APIClient

        resp = APIClient().get(self.ME_URL)
        assert resp.status_code in (401, 403)

    def test_refresh_rotates_access_token(self) -> None:
        """POST /api/auth/refresh renueva el access usando la cookie.

        Regresión del 500 por pasar el ''user_id'' como string a
        ``RefreshToken.for_user``.
        """
        from rest_framework.test import APIClient

        user = UserFactory(email="rotador@example.com")
        client = APIClient()
        login = client.post(self.LOGIN_URL, {"email": "rotador@example.com", "password": "test-password-123"})
        assert login.status_code == 200

        client.cookies["refresh_token"] = login.cookies["refresh_token"]
        resp = client.post("/api/auth/refresh")
        assert resp.status_code == 200
        assert resp.data["access"]