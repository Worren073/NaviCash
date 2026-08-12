"""views — Endpoints de ``accounts``: registro, login, refresh, logout, perfil.

La autenticación usa SimpleJWT con la siguiente división de responsabilidades:
- El **access token** (corto, 15 min) viaja en ``Authorization: Bearer ...``.
- El **refresh token** (largo, 30 días) viaja en una **cookie httpOnly**
  llamada ``refresh_token`` restringida a ``/api/auth/`` (no accesible a JS,
  protegiendo contra XSS — ver RNF-01).
"""

from __future__ import annotations

import logging

from django.conf import settings

logger = logging.getLogger(__name__)
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.emails import send_password_reset_email
from apps.accounts.models import LegalDocument, PasswordResetToken, User
from apps.accounts.serializers import (
    AcceptTermsSerializer,
    ChangePasswordSerializer,
    ForgotPasswordSerializer,
    LegalDocumentSerializer,
    LoginSerializer,
    RegisterSerializer,
    ResetPasswordSerializer,
    UserSerializer,
    UserUpdateSerializer,
    VerifyEmailSerializer,
)


def _set_refresh_cookie(response: Response, token: RefreshToken) -> Response:
    """Coloca el refresh token en la cookie httpOnly de la respuesta.

    Args:
        response: respuesta HTTP a modificar.
        token: objeto RefreshToken (o string de refresh).

    Returns:
        La misma ``response`` con la cookie seteada.
    """
    cookie_conf = settings.SIMPLE_JWT
    response.set_cookie(
        key=cookie_conf["AUTH_COOKIE"],
        value=str(token),
        max_age=cookie_conf["REFRESH_TOKEN_LIFETIME"].total_seconds(),
        httponly=cookie_conf["AUTH_COOKIE_HTTP_ONLY"],
        secure=cookie_conf["AUTH_COOKIE_SECURE"],
        samesite=cookie_conf["AUTH_COOKIE_SAMESITE"],
        path=cookie_conf["AUTH_COOKIE_PATH"],
    )
    return response


def _clear_refresh_cookie(response: Response) -> Response:
    """Elimina la cookie de refresh de la respuesta (logout)."""
    response.delete_cookie(settings.SIMPLE_JWT["AUTH_COOKIE"], path=settings.SIMPLE_JWT["AUTH_COOKIE_PATH"])
    return response


def _revoke_refresh_family(user: User) -> None:
    """Revoca todos los refresh outstanding (no expirados) de un usuario.

    Borrar los ``OutstandingToken`` activos equivale a blacklistear cada uno:
    los registros de ``BlacklistedToken`` referencian su outstanding con
    CASCADE, así que desaparecen con él. Idempotente (borrar 0 filas es válido).
    """
    OutstandingToken.objects.filter(user=user, expires_at__gt=timezone.now()).delete()


class RegisterView(APIView):
    """Crea una cuenta nueva y envía el correo de verificación.

    Respuesta 201 con ``{detail, token_de_verificacion?}``.
    En modo debug se devuelve ``debug_token`` para facilitar las pruebas locales
    (en producción ese campo no existe).
    Si el email ya está registrado se responde igual que el éxito (mismo status
    y mensaje genérico) para no enumerar cuentas — AUDIT B5.
    """

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "register"

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if serializer.email_already_registered:
            # B5: respuesta idéntica al éxito; no se crea ni se envía correo.
            logger.info(
                "REGISTER_DUPLICATE email=%s (no se envia correo, B5)",
                serializer.validated_data.get("email", "?"),
            )
            return Response(
                {
                    "detail": "Revisa tu correo para continuar.",
                    "email_verification_required": settings.EMAIL_VERIFICATION_REQUIRED,
                },
                status=status.HTTP_201_CREATED,
            )
        user = serializer.save()
        logger.info(
            "REGISTER_CREATED email=%s user=%s",
            serializer.validated_data.get("email", "?"),
            user.id,
        )
        payload = {
            "detail": "Revisa tu correo para continuar.",
            "email_verification_required": settings.EMAIL_VERIFICATION_REQUIRED,
        }
        if settings.DEBUG and settings.EMAIL_VERIFICATION_REQUIRED:
            verification = user.verification
            payload["debug_token"] = verification.plain_token
        return Response(payload, status=status.HTTP_201_CREATED)


class LoginView(APIView):
    """Inicia sesión con email + contraseña.

    Comportamiento:
        - Devuelve ``access`` en el body (corto).
        - Guarda ``refresh_token`` en cookie httpOnly.
        - Si la cuenta no está verificada responde 401 con code ``not_verified``.
    """

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]

        refresh = RefreshToken.for_user(user)
        response = Response(
            {
                "access": str(refresh.access_token),
                "user": UserSerializer(user).data,
            },
            status=status.HTTP_200_OK,
        )
        return _set_refresh_cookie(response, refresh)


class RefreshView(APIView):
    """Renueva el access token usando el refresh de la cookie.

    Rotación segura (AUDIT C3/A7): el refresh usado se comprueba contra la
    blacklist (reuse-detection), la cuenta debe seguir activa, y el token se
    blacklistea ANTES de emitir el nuevo. Cualquier anomalía → 401.
    """

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request):
        cookie_name = settings.SIMPLE_JWT["AUTH_COOKIE"]
        refresh_value = request.COOKIES.get(cookie_name)
        if not refresh_value:
            return Response(
                {"detail": "No hay sesión refrescable."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        try:
            refresh = RefreshToken(refresh_value)
            refresh.check_blacklist()
            user = User.objects.get(pk=refresh["user_id"])
            if not user.is_active:
                # Cuenta desactivada: no debe poder renovar sesiones (A7).
                raise TokenError("Cuenta inactiva.")
            if not OutstandingToken.objects.filter(user=user, jti=refresh["jti"]).exists():
                # Reuse-detection (C3): si la familia fue revocada/logout y el
                # OutstandingToken ya no existe, ``blacklist()`` lo recrearía.
                # Rechazar aquí impide revivir un refresh borrado.
                raise TokenError("Sesión revocada.")
            refresh.blacklist()
            new_refresh = RefreshToken.for_user(user)
        except (ObjectDoesNotExist, KeyError, TokenError):
            return Response(
                {"detail": "Sesión inválida o expirada."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        response = Response({"access": str(new_refresh.access_token)}, status=status.HTTP_200_OK)
        return _set_refresh_cookie(response, new_refresh)


class LogoutView(APIView):
    """Cierra sesión: revoca la familia de refresh del usuario y borra la cookie.

    Requiere estar autenticado (tener un access valido). Además de blacklistear
    el refresh de la cookie, se revocan TODOS los refresh outstanding de la
    cuenta (otros dispositivos también se cierran) — AUDIT C3.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        cookie_name = settings.SIMPLE_JWT["AUTH_COOKIE"]
        refresh_value = request.COOKIES.get(cookie_name)
        if refresh_value:
            try:
                RefreshToken(refresh_value).blacklist()
            except Exception:
                # Token ya en blacklist o inválido: no es un error fatal.
                pass
        _revoke_refresh_family(request.user)
        response = Response({"detail": "Sesión cerrada."}, status=status.HTTP_200_OK)
        return _clear_refresh_cookie(response)


class VerifyEmailView(APIView):
    """Activa la cuenta verificando el token del correo.

    Body: ``{ "token": "..." }``. Respuesta 200 con el perfil activo.
    """

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "email_verify"

    def post(self, request):
        serializer = VerifyEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response({"detail": "Cuenta verificada.", "user": UserSerializer(user).data})


class ForgotPasswordView(APIView):
    """Solicita el enlace de recuperación de contraseña (M13).

    La respuesta es SIEMPRE la misma (AUDIT B5): no revela si el correo está
    registrado. Solo se crea el token y se envía el correo si existe la cuenta.
    """

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = User.objects.filter(email__iexact=serializer.validated_data["email"]).first()
        if user:
            reset = PasswordResetToken.create_for_user(user)
            send_password_reset_email(user.email, reset.plain_token)
        return Response(
            {
                "detail": (
                    "Si el correo está registrado, te enviaremos un enlace "
                    "para restablecer tu contraseña."
                )
            },
            status=status.HTTP_200_OK,
        )


class ResetPasswordView(APIView):
    """Restablece la contraseña con el token del correo (one-time).

    No autentica al usuario: debe iniciar sesión con la nueva contraseña.
    Al usarse, el token queda invalidado y se revoca la familia de refresh.
    """

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        _revoke_refresh_family(user)
        return Response(
            {"detail": "Contraseña restablecida. Inicia sesión con tu nueva contraseña."},
            status=status.HTTP_200_OK,
        )


class ChangePasswordView(APIView):
    """Cambia la contraseña estando autenticado (access Bearer).

    Verifica la contraseña actual y revoca la familia de refresh para forzar
    un nuevo inicio de sesión en todos los dispositivos.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, user=request.user)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        _revoke_refresh_family(request.user)
        return Response(
            {"detail": "Contraseña actualizada. Inicia sesión de nuevo en otros dispositivos."},
            status=status.HTTP_200_OK,
        )


class MeView(APIView):
    """Devuelve el perfil del usuario autenticado (token Bearer)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)

    def patch(self, request):
        """Actualiza el perfil (nombre, moneda base, idioma, zona, recordatorio)."""
        serializer = UserUpdateSerializer(
            request.user, data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(UserSerializer(request.user).data)


class LegalDocumentListView(APIView):
    """Lista los documentos legales activos (términos, privacidad).

    Público: no requiere autenticación. Devuelve la versión activa de cada tipo.
    """

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "assistant"

    def get(self, request):
        docs = LegalDocument.objects.filter(is_active=True).order_by("doc_type")
        serializer = LegalDocumentSerializer(docs, many=True)
        return Response(serializer.data)


class LegalDocumentDetailView(APIView):
    """Detalle de un documento legal específico (versión activa por tipo).

    Público: no requiere autenticación. El ``doc_type`` viene en la URL.
    """

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "assistant"

    def get(self, request, doc_type: str):
        doc = LegalDocument.objects.filter(doc_type=doc_type, is_active=True).first()
        if not doc:
            return Response(
                {"detail": "Documento no encontrado."},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = LegalDocumentSerializer(doc)
        return Response(serializer.data)


class UserLegalAcceptanceView(APIView):
    """Historial de aceptación de términos del usuario autenticado.

    Devuelve cuándo y qué versión aceptó el usuario al registrarse.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        return Response(
            {
                "accepted_terms_at": user.accepted_terms_at,
                "accepted_terms_version": user.accepted_terms_version,
                "current_terms_version": settings.TERMS_VERSION,
                "needs_reacceptance": user.accepted_terms_version != settings.TERMS_VERSION,
            }
        )


class AcceptTermsView(APIView):
    """Registra la (re)aceptación de los Términos vigentes por parte del usuario.

    Autenticado. La versión aceptada siempre es la activa del servidor
    (``settings.TERMS_VERSION``); el cliente no puede enviar una versión a medida,
    evitando forjar aceptaciones de versiones anteriores (A6).
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "register"

    def post(self, request):
        serializer = AcceptTermsSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        user = request.user
        return Response(
            {
                "detail": "Términos y condiciones aceptados.",
                "accepted_terms_at": user.accepted_terms_at,
                "accepted_terms_version": user.accepted_terms_version,
            },
            status=status.HTTP_200_OK,
        )