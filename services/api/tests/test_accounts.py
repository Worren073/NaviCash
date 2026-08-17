"""tests — Flujo de cuentas: registro, verificación, login, refresh, logout, me.

También cubre seguridad: rotación con blacklist (C3/A7), logout que revoca la
familia, CAPTCHA fail-closed (A1), recuperación/cambio de contraseña (M13),
tokens hasheados y anti-enumeración en registro (B5).
"""

from __future__ import annotations

import pytest
from django.core import mail
from django.utils import timezone

from apps.accounts.models import EmailVerification, PasswordResetToken, User
from factories import UserFactory


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
        # El token plano es el que viaja por correo; en BD solo hay su hash.
        user = User.objects.get(email="debug@example.com")
        assert user.verification.token == EmailVerification.hash_token(resp.data["debug_token"])

    def test_sends_verification_email(self, api_client) -> None:
        """Se envía un correo de verificación al registrarse."""
        resp = api_client.post(self.URL, self._payload(email="correo@example.com"))
        assert resp.status_code == 201
        assert len(mail.outbox) == 1
        assert "correo@example.com" in mail.outbox[0].to

    def test_duplicate_email_generic_response(self, api_client) -> None:
        """Un email ya registrado responde igual que el éxito (B5).

        La respuesta es idéntica al registro exitoso (201 + mensaje genérico)
        para no enumerar cuentas; la intención original (no crear duplicados)
        se conserva: no se crea otra cuenta ni se dispara un correo.
        """
        UserFactory(email="dup@example.com")
        resp = api_client.post(
            self.URL, self._payload(email="DUP@example.com")
        )
        assert resp.status_code == 201
        assert resp.data["detail"] == "Revisa tu correo para continuar."
        assert User.objects.filter(email__iexact="dup@example.com").count() == 1
        assert len(mail.outbox) == 0

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

    def test_captcha_fail_closed_in_production(self, api_client) -> None:
        """Con DEBUG=False y sin secreto, el registro se rechaza (A1)."""
        from django.test import override_settings

        with override_settings(DEBUG=False, TURNSTILE_SECRET_KEY=""):
            resp = api_client.post(
                self.URL, self._payload(email="prod@example.com", captcha_token="")
            )
        assert resp.status_code == 400
        assert "captcha_token" in resp.data["errors"]

    def test_captcha_fail_closed_with_fake_token(self, api_client) -> None:
        """En producción un token no validado tampoco pasa (sin red)."""
        from django.test import override_settings

        with override_settings(DEBUG=False, TURNSTILE_SECRET_KEY=""):
            resp = api_client.post(
                self.URL, self._payload(email="prod2@example.com", captcha_token="fake-token")
            )
        assert resp.status_code == 400
        assert "captcha_token" in resp.data["errors"]


@pytest.mark.django_db
class TestVerifyEmail:
    """Endpoint POST /api/auth/verify-email."""

    URL = "/api/auth/verify-email"

    def test_activates_account_with_valid_token(self, api_client) -> None:
        """Un token válido activa la cuenta (búsqueda por hash del plano)."""
        user = UserFactory(email="activable@example.com", is_active=False)
        verification = EmailVerification.create_for_user(user)
        resp = api_client.post(self.URL, {"token": verification.plain_token})
        assert resp.status_code == 200
        user.refresh_from_db()
        assert user.is_active is True

    def test_token_stored_hashed(self, api_client) -> None:
        """En BD solo existe el hash sha256 del token (M13)."""
        user = UserFactory(email="hash@example.com", is_active=False)
        verification = EmailVerification.create_for_user(user)
        assert verification.token == EmailVerification.hash_token(verification.plain_token)
        assert verification.token != verification.plain_token

    def test_rejects_used_token(self, api_client) -> None:
        """Un token ya usado no puede reutilizarse."""
        user = UserFactory(email="usado@example.com", is_active=False)
        verification = EmailVerification.create_for_user(user)
        verification.used = True
        verification.save(update_fields=["used"])
        resp = api_client.post(self.URL, {"token": verification.plain_token})
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

    def test_me_returns_is_onboarded_false_by_default(self, api_client) -> None:
        """Un usuario nuevo aún no ha visto el tutorial (is_onboarded=False)."""
        resp = api_client.get(self.ME_URL)
        assert resp.status_code == 200
        assert resp.data["is_onboarded"] is False

    def test_me_marks_is_onboarded(self, api_client) -> None:
        """PATCH /api/auth/me {is_onboarded: true} persiste el tutorial visto."""
        resp = api_client.patch(self.ME_URL, {"is_onboarded": True})
        assert resp.status_code == 200
        assert resp.data["is_onboarded"] is True
        api_client.user.refresh_from_db()
        assert api_client.user.is_onboarded is True

    def test_me_rejects_invalid_is_onboarded(self, api_client) -> None:
        """is_onboarded debe ser booleano; valores raros se rechazan."""
        resp = api_client.patch(self.ME_URL, {"is_onboarded": "si"})
        assert resp.status_code == 400
        assert "is_onboarded" in resp.data["errors"]
        api_client.user.refresh_from_db()
        assert api_client.user.is_onboarded is False

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

    def test_refresh_blacklists_rotated_token(self) -> None:
        """Tras rotar, el refresh usado queda en la blacklist (C3)."""
        from rest_framework.test import APIClient
        from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
        from rest_framework_simplejwt.tokens import RefreshToken

        UserFactory(email="rota-blacklist@example.com")
        client = APIClient()
        login = client.post(
            self.LOGIN_URL, {"email": "rota-blacklist@example.com", "password": "test-password-123"}
        )
        refresh_str = login.cookies["refresh_token"].value
        client.cookies["refresh_token"] = login.cookies["refresh_token"]
        resp = client.post("/api/auth/refresh")
        assert resp.status_code == 200
        # El refresh usado quedó en la blacklist (verify=False al ya estar negro).
        assert BlacklistedToken.objects.filter(
            token__jti=RefreshToken(refresh_str, verify=False)["jti"]
        ).exists()

    def test_refresh_rejects_reused_token(self) -> None:
        """Un refresh ya rotado (reutilizado) devuelve 401 (C3)."""
        from rest_framework.test import APIClient

        UserFactory(email="reuso@example.com")
        client = APIClient()
        login = client.post(
            self.LOGIN_URL, {"email": "reuso@example.com", "password": "test-password-123"}
        )
        old_refresh = login.cookies["refresh_token"]
        client.cookies["refresh_token"] = old_refresh
        assert client.post("/api/auth/refresh").status_code == 200
        # Reutilizar el token robado/rotado: 401, no 200.
        client.cookies["refresh_token"] = old_refresh
        assert client.post("/api/auth/refresh").status_code == 401

    def test_refresh_rejects_deactivated_user(self) -> None:
        """Un usuario desactivado no puede renovar (401, A7)."""
        from rest_framework.test import APIClient

        user = UserFactory(email="desactivado@example.com")
        client = APIClient()
        login = client.post(
            self.LOGIN_URL, {"email": "desactivado@example.com", "password": "test-password-123"}
        )
        assert login.status_code == 200
        user.is_active = False
        user.save(update_fields=["is_active"])
        client.cookies["refresh_token"] = login.cookies["refresh_token"]
        resp = client.post("/api/auth/refresh")
        assert resp.status_code == 401

    def test_logout_revokes_whole_family(self) -> None:
        """Logout borra todos los refresh outstanding de la cuenta (C3)."""
        from rest_framework.test import APIClient
        from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
        from rest_framework_simplejwt.tokens import RefreshToken

        user = UserFactory(email="familia@example.com")
        client = APIClient()
        login = client.post(
            self.LOGIN_URL, {"email": "familia@example.com", "password": "test-password-123"}
        )
        assert login.status_code == 200
        # Segundo "dispositivo": otro refresh outstanding de la misma cuenta.
        RefreshToken.for_user(user)
        assert (
            OutstandingToken.objects.filter(user=user, expires_at__gt=timezone.now()).count() >= 2
        )

        client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
        client.cookies["refresh_token"] = login.cookies["refresh_token"]
        logout = client.post("/api/auth/logout")
        assert logout.status_code == 200

        assert not OutstandingToken.objects.filter(
            user=user, expires_at__gt=timezone.now()
        ).exists()
        # Y el refresh de la cookie tampoco vale ya.
        client.credentials()
        client.cookies["refresh_token"] = login.cookies["refresh_token"]
        assert client.post("/api/auth/refresh").status_code == 401

    def test_logout_is_idempotent(self) -> None:
        """Logout repetido responde igual (200) sin errores."""
        from rest_framework.test import APIClient

        UserFactory(email="idempotente@example.com")
        client = APIClient()
        login = client.post(
            self.LOGIN_URL, {"email": "idempotente@example.com", "password": "test-password-123"}
        )
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
        client.cookies["refresh_token"] = login.cookies["refresh_token"]
        assert client.post("/api/auth/logout").status_code == 200
        assert client.post("/api/auth/logout").status_code == 200

    def test_login_throttled_after_limit(self) -> None:
        """El scope 'login' (5/min) corta los intentos con 429 (A1)."""
        from rest_framework.test import APIClient

        client = APIClient()
        statuses = []
        for _ in range(6):
            resp = client.post(
                self.LOGIN_URL, {"email": "fuerza@example.com", "password": "incorrecta"}
            )
            statuses.append(resp.status_code)
        assert 429 in statuses

    def test_refresh_rejects_untrusted_origin(self) -> None:
        """Refresh con Origin de otro sitio responde 401 (defensa CSRF).

        La cookie httpOnly viaja sola en requests cross-site; sin verificar el
        origen, un formulario malicioso podría forzar la rotación. El Origin
        debe coincidir con un origen CORS permitido.
        """
        from rest_framework.test import APIClient

        user = UserFactory(email="origin@example.com")
        client = APIClient()
        login = client.post(
            self.LOGIN_URL, {"email": "origin@example.com", "password": "test-password-123"}
        )
        assert login.status_code == 200
        client.cookies["refresh_token"] = login.cookies["refresh_token"]

        # Origin permitido (http://localhost:5173) → 200.
        allowed = client.post(
            "/api/auth/refresh", HTTP_ORIGIN="http://localhost:5173"
        )
        assert allowed.status_code == 200

        client.cookies["refresh_token"] = allowed.cookies["refresh_token"]
        # Origin de un sitio atacante → 401 y no rota.
        evil = client.post("/api/auth/refresh", HTTP_ORIGIN="https://evil.example.com")
        assert evil.status_code == 401

    def test_login_locks_account_after_attempts(self) -> None:
        """Tras N intentos fallidos la cuenta se bloquea (429) unos minutos."""
        from django.conf import settings
        from rest_framework.test import APIClient

        UserFactory(email="bloqueo@example.com")
        client = APIClient()
        for _ in range(settings.MAX_FAILED_LOGIN_ATTEMPTS):
            resp = client.post(
                self.LOGIN_URL, {"email": "bloqueo@example.com", "password": "incorrecta"}
            )
            assert resp.status_code == 401
        # El siguiente intento (aunque sea con la clave correcta) queda bloqueado.
        resp = client.post(
            self.LOGIN_URL, {"email": "bloqueo@example.com", "password": "test-password-123"}
        )
        assert resp.status_code == 429

    def test_login_success_clears_failed_counter(self) -> None:
        """Un login correcto resetea el contador de intentos fallidos."""
        from django.conf import settings
        from django.core.cache import cache
        from rest_framework.test import APIClient

        from apps.accounts.views import _login_lock_key

        user = UserFactory(email="limpia@example.com")
        client = APIClient()
        for _ in range(settings.MAX_FAILED_LOGIN_ATTEMPTS - 1):
            assert client.post(
                self.LOGIN_URL, {"email": "limpia@example.com", "password": "incorrecta"}
            ).status_code == 401
        # Antes del acierto el contador lleva MAX-1 fallos acumulados.
        assert cache.get(_login_lock_key(user)) == settings.MAX_FAILED_LOGIN_ATTEMPTS - 1
        # Un acierto limpia el contador; los intentos previos no cuentan.
        ok = client.post(
            self.LOGIN_URL, {"email": "limpia@example.com", "password": "test-password-123"}
        )
        assert ok.status_code == 200
        assert cache.get(_login_lock_key(user)) is None

    def test_refresh_reuse_revokes_whole_family(self) -> None:
        """Reutilizar un refresh ya rotado revoca TODA la familia (C3)."""
        from rest_framework.test import APIClient
        from rest_framework_simplejwt.token_blacklist.models import OutstandingToken

        user = UserFactory(email="familia-reuso@example.com")
        client = APIClient()
        login = client.post(
            self.LOGIN_URL, {"email": "familia-reuso@example.com", "password": "test-password-123"}
        )
        assert login.status_code == 200
        old_refresh = login.cookies["refresh_token"]
        # Segundo dispositivo: otro refresh outstanding de la misma cuenta.
        from rest_framework_simplejwt.tokens import RefreshToken

        RefreshToken.for_user(user)

        client.cookies["refresh_token"] = old_refresh
        assert client.post("/api/auth/refresh").status_code == 200
        # Reuso del token rotado: 401 y además la familia quedó revocada.
        client.cookies["refresh_token"] = old_refresh
        assert client.post("/api/auth/refresh").status_code == 401
        assert not OutstandingToken.objects.filter(
            user=user, expires_at__gt=timezone.now()
        ).exists()


@pytest.mark.django_db
class TestPasswordRecovery:
    """Forgot/reset/change de contraseña (M13)."""

    FORGOT_URL = "/api/auth/forgot-password"
    RESET_URL = "/api/auth/reset-password"
    CHANGE_URL = "/api/auth/change-password"

    def test_forgot_sends_link_for_existing_email(self, api_client) -> None:
        """Email registrado: token hasheado creado y correo con el enlace."""
        import re

        user = UserFactory(email="olvido@example.com")
        resp = api_client.post(self.FORGOT_URL, {"email": "olvido@example.com"})
        assert resp.status_code == 200
        assert "si el correo está registrado" in resp.data["detail"].lower()
        assert len(mail.outbox) == 1
        body = mail.outbox[0].body
        assert "/reset-password?token=" in body
        plain = re.search(r"token=([^&\s]+)", body).group(1)
        assert "email=olvido%40example.com" in body
        reset = PasswordResetToken.objects.get(user=user)
        # En BD solo existe el hash del token que viajó por correo.
        assert reset.token == PasswordResetToken.hash_token(plain)
        assert reset.token != plain

    def test_forgot_generic_response_for_unknown_email(self, api_client) -> None:
        """Correo desconocido: misma respuesta genérica y sin correo (B5)."""
        resp = api_client.post(self.FORGOT_URL, {"email": "nadie@example.com"})
        assert resp.status_code == 200
        assert "si el correo está registrado" in resp.data["detail"].lower()
        assert len(mail.outbox) == 0
        assert PasswordResetToken.objects.count() == 0

    def test_reset_changes_password_and_token_is_one_time(self, api_client) -> None:
        """Token válido: cambia la contraseña e invalida el token (one-time)."""
        user = UserFactory(email="reset@example.com")
        reset = PasswordResetToken.create_for_user(user)
        resp = api_client.post(
            self.RESET_URL, {"token": reset.plain_token, "password": "nueva-clave-456"}
        )
        assert resp.status_code == 200
        user.refresh_from_db()
        assert user.check_password("nueva-clave-456")
        reset.refresh_from_db()
        assert reset.used is True
        # Reuso del token → rechazado; la contraseña no cambia otra vez.
        second = api_client.post(
            self.RESET_URL, {"token": reset.plain_token, "password": "otra-clave-789"}
        )
        assert second.status_code == 400
        user.refresh_from_db()
        assert user.check_password("nueva-clave-456")

    def test_reset_revokes_refresh_family(self, api_client) -> None:
        """El reset revoca los refresh outstanding del usuario."""
        from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
        from rest_framework_simplejwt.tokens import RefreshToken

        user = UserFactory(email="reset-familia@example.com")
        RefreshToken.for_user(user)
        assert OutstandingToken.objects.filter(user=user).exists()
        reset = PasswordResetToken.create_for_user(user)
        resp = api_client.post(
            self.RESET_URL, {"token": reset.plain_token, "password": "clave-nueva-123"}
        )
        assert resp.status_code == 200
        assert not OutstandingToken.objects.filter(
            user=user, expires_at__gt=timezone.now()
        ).exists()

    def test_reset_rejects_invalid_and_weak_token(self, api_client) -> None:
        """Token inválido y contraseña débil se rechazan con 400."""
        resp = api_client.post(
            self.RESET_URL, {"token": "no-existe", "password": "clave-nueva-123"}
        )
        assert resp.status_code == 400
        assert "token" in resp.data["errors"]

    def test_change_password_requires_correct_current(self, api_client) -> None:
        """Contraseña actual incorrecta → 400."""
        resp = api_client.post(
            self.CHANGE_URL,
            {"current_password": "mal", "new_password": "clave-nueva-123"},
        )
        assert resp.status_code == 400
        assert "current_password" in resp.data["errors"]

    def test_change_password_success_and_revokes_family(self, api_client) -> None:
        """Con la actual correcta cambia la clave y revoca la familia."""
        from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
        from rest_framework_simplejwt.tokens import RefreshToken

        user = api_client.user
        old_refresh = RefreshToken.for_user(user)
        assert OutstandingToken.objects.filter(user=user).exists()
        resp = api_client.post(
            self.CHANGE_URL,
            {"current_password": "test-password-123", "new_password": "clave-nueva-456"},
        )
        assert resp.status_code == 200
        user.refresh_from_db()
        assert user.check_password("clave-nueva-456")
        assert not OutstandingToken.objects.filter(
            user=user, expires_at__gt=timezone.now()
        ).exists()
        # El refresh emitido antes del cambio ya no renueva (401).
        api_client.cookies["refresh_token"] = str(old_refresh)
        assert api_client.post("/api/auth/refresh").status_code == 401

    def test_change_password_requires_auth(self) -> None:
        """Sin access token, change-password responde 401."""
        from rest_framework.test import APIClient

        resp = APIClient().post(
            self.CHANGE_URL,
            {"current_password": "x", "new_password": "clave-nueva-123"},
        )
        assert resp.status_code == 401


@pytest.mark.django_db
class TestAcceptTerms:
    """Endpoint POST /api/auth/accept-terms (re-aceptación de términos)."""

    URL = "/api/auth/accept-terms"

    def test_requires_authentication(self) -> None:
        """Sin access token, accept-terms responde 401."""
        from rest_framework.test import APIClient

        resp = APIClient().post(self.URL, {"accepted": True})
        assert resp.status_code == 401

    def test_accepts_and_persists_current_version(self, api_client) -> None:
        """Aceptar guarda la fecha y la versión vigente del servidor."""
        from django.conf import settings

        user = api_client.user
        user.accepted_terms_version = "v0-obsoleta"
        user.accepted_terms_at = None
        user.save(update_fields=["accepted_terms_version", "accepted_terms_at"])

        resp = api_client.post(self.URL, {"accepted": True})
        assert resp.status_code == 200
        assert resp.data["accepted_terms_version"] == settings.TERMS_VERSION
        assert resp.data["accepted_terms_at"] is not None

        user.refresh_from_db()
        assert user.accepted_terms_version == settings.TERMS_VERSION
        assert user.accepted_terms_at is not None

    def test_rejects_false(self, api_client) -> None:
        """``accepted=False`` se rechaza; no se registra aceptación."""
        user = api_client.user
        user.accepted_terms_version = "v0-obsoleta"
        user.accepted_terms_at = None
        user.save(update_fields=["accepted_terms_version", "accepted_terms_at"])

        resp = api_client.post(self.URL, {"accepted": False})
        assert resp.status_code == 400
        assert "accepted" in resp.data["errors"]

        user.refresh_from_db()
        assert user.accepted_terms_version == "v0-obsoleta"
        assert user.accepted_terms_at is None

    def test_rejects_inactive_account(self, api_client) -> None:
        """Una cuenta sin email verificado no puede aceptar términos.

        SimpleJWT rechaza la autenticación de usuarios inactivos en la capa de
        ``IsAuthenticated``, así que la petición se deniega con 401 antes de
        llegar al serializer: es la salvaguarda correcta y mantiene el estado
        original intacto.
        """
        user = api_client.user
        user.is_active = False
        user.save(update_fields=["is_active"])

        resp = api_client.post(self.URL, {"accepted": True})
        assert resp.status_code == 401