"""accounts — Usuarios, registro, verificación de email y autenticación JWT.

Flujo de registro:
1. ``POST /api/auth/register`` crea el usuario con ``is_active=False`` y
   genera un token de verificación (caduca en 24 h).
2. El email con el enlace/token se envía (consola en dev, SMTP en prod).
3. ``POST /api/auth/verify-email`` activa la cuenta (``is_active=True``).
4. ``POST /api/auth/login`` devuelve el access token y guarda el refresh en
   una cookie ``httpOnly``.
5. ``POST /api/auth/refresh`` renueva el access leyendo la cookie (rotación
   con blacklist del token usado).
6. ``POST /api/auth/logout`` invalida la familia de refresh y limpia la cookie.
7. ``GET /api/auth/me`` devuelve el perfil del usuario autenticado.

Recuperación de contraseña (M13):
8. ``POST /api/auth/forgot-password`` solicita el enlace (respuesta genérica).
9. ``POST /api/auth/reset-password`` cambia la contraseña con el token one-time.
10. ``POST /api/auth/change-password`` cambia la contraseña autenticado.
"""

from apps.accounts.views import (  # noqa: F401
    AcceptTermsView,
    CancelAccountDeletionView,
    ChangePasswordView,
    DeleteAccountView,
    ForgotPasswordView,
    LegalDocumentDetailView,
    LegalDocumentListView,
    LoginView,
    LogoutView,
    MeView,
    RefreshView,
    RegisterView,
    ResetPasswordView,
    UserLegalAcceptanceView,
    VerifyEmailView,
)
from django.urls import path

urlpatterns = [
    path("auth/register", RegisterView.as_view(), name="auth-register"),
    path("auth/login", LoginView.as_view(), name="auth-login"),
    path("auth/refresh", RefreshView.as_view(), name="auth-refresh"),
    path("auth/logout", LogoutView.as_view(), name="auth-logout"),
    path("auth/verify-email", VerifyEmailView.as_view(), name="auth-verify-email"),
    path("auth/forgot-password", ForgotPasswordView.as_view(), name="auth-forgot-password"),
    path("auth/reset-password", ResetPasswordView.as_view(), name="auth-reset-password"),
    path("auth/change-password", ChangePasswordView.as_view(), name="auth-change-password"),
    path("auth/me", MeView.as_view(), name="auth-me"),
    # Eliminación de cuenta (período de gracia cancelable)
    path("auth/delete-account", DeleteAccountView.as_view(), name="auth-delete-account"),
    path(
        "auth/cancel-account-deletion",
        CancelAccountDeletionView.as_view(),
        name="auth-cancel-account-deletion",
    ),
    # Documentos legales (públicos)
    path("legal", LegalDocumentListView.as_view(), name="legal-list"),
    path("legal/<str:doc_type>", LegalDocumentDetailView.as_view(), name="legal-detail"),
    # Aceptación de términos del usuario
    path("auth/legal-acceptance", UserLegalAcceptanceView.as_view(), name="auth-legal-acceptance"),
    path("auth/accept-terms", AcceptTermsView.as_view(), name="auth-accept-terms"),
]