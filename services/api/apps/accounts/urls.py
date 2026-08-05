"""accounts — Usuarios, registro, verificación de email y autenticación JWT.

Flujo de registro:
1. ``POST /api/auth/register`` crea el usuario con ``is_active=False`` y
   genera un token de verificación (caduca en 24 h).
2. El email con el enlace/token se envía (consola en dev, SMTP en prod).
3. ``POST /api/auth/verify-email`` activa la cuenta (``is_active=True``).
4. ``POST /api/auth/login`` devuelve el access token y guarda el refresh en
   una cookie ``httpOnly``.
5. ``POST /api/auth/refresh`` renueva el access leyendo la cookie.
6. ``POST /api/auth/logout`` invalida el refresh (blacklist) y limpia la cookie.
7. ``GET /api/auth/me`` devuelve el perfil del usuario autenticado.
"""

from apps.accounts.views import (  # noqa: F401
    LoginView,
    LogoutView,
    MeView,
    RefreshView,
    RegisterView,
    VerifyEmailView,
)
from django.urls import path

urlpatterns = [
    path("auth/register", RegisterView.as_view(), name="auth-register"),
    path("auth/login", LoginView.as_view(), name="auth-login"),
    path("auth/refresh", RefreshView.as_view(), name="auth-refresh"),
    path("auth/logout", LogoutView.as_view(), name="auth-logout"),
    path("auth/verify-email", VerifyEmailView.as_view(), name="auth-verify-email"),
    path("auth/me", MeView.as_view(), name="auth-me"),
]