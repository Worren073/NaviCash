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
sec_logger = logging.getLogger("apps.accounts.security")
from django.core.exceptions import ObjectDoesNotExist
from django.core.cache import cache
from datetime import datetime
from urllib.parse import urlsplit

from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.emails import (
    send_account_deletion_cancelled_email,
    send_account_deletion_email,
    send_password_reset_email,
)
from apps.accounts.models import LegalDocument, PasswordResetToken, User
from apps.accounts.serializers import (
    AcceptTermsSerializer,
    ChangePasswordSerializer,
    DeleteAccountSerializer,
    ForgotPasswordSerializer,
    LegalDocumentSerializer,
    LoginSerializer,
    RegisterSerializer,
    ResetPasswordSerializer,
    UserSerializer,
    UserUpdateSerializer,
    VerifyEmailSerializer,
)
from apps.accounts.services import (
    cancel_account_deletion,
    maybe_purge_daily,
    schedule_account_deletion,
)
from apps.notifications.models import Notification


def _record_outstanding(user: User, refresh: RefreshToken) -> None:
    """Registra un ``OutstandingToken`` para el refresh emitido.

    La reuse-detection de ``RefreshView`` exige que el ``OutstandingToken`` del
    refresh exista. ``RefreshToken.for_user`` no lo crea por sí solo en estos
    flujos manuales, así que se registra aquí tanto en login como en rotación.
    """
    OutstandingToken.objects.get_or_create(
        jti=refresh["jti"],
        defaults={
            "user": user,
            "token": str(refresh),
            "expires_at": datetime.fromtimestamp(
                refresh["exp"], tz=timezone.get_current_timezone()
            ),
        },
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


def _origin_is_allowed(request) -> bool:
    """Comprueba que el Origin/Referer del request esté permitido (defensa CSRF).

    El navegador siempre adjunta ``Origin`` (o ``Referer``) en las peticiones
    cross-site; si no coincide con un origen CORS permitido, la petición no
    viene de nuestra SPA y se rechaza. Clientes no-navegador (curl, móvil) que
    no envían cabecera de origen pasan (el JWT/cookie ya no se expone a ellos).
    """
    origin = request.META.get("HTTP_ORIGIN") or request.META.get("HTTP_REFERER")
    if not origin:
        return True
    parts = urlsplit(origin)
    if not parts.scheme or not parts.netloc:
        return False
    normalized = f"{parts.scheme}://{parts.netloc}".rstrip("/")
    return normalized in set(settings.CORS_ALLOWED_ORIGINS or [])


def _login_lock_key(user: User) -> str:
    """Clave de caché del contador de intentos fallidos de login de la cuenta."""
    return f"login_failed:{user.pk}"


def _delete_lock_key(user: User) -> str:
    """Clave de caché del contador de intentos fallidos de eliminación."""
    return f"delete_failed:{user.pk}"


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
        email = (request.data.get("email") or "").strip().lower()
        target = User.objects.filter(email__iexact=email).first()

        # Lockout por cuenta (AUDIT A1): tras N intentos fallidos la cuenta se
        # bloquea unos minutos. Los contadores viven en la caché compartida
        # (Redis en prod), así el bloqueo aplica aunque cambie el worker.
        lock_key = _login_lock_key(target) if target else None
        if lock_key:
            failures = cache.get(lock_key, 0)
            if failures >= settings.MAX_FAILED_LOGIN_ATTEMPTS:
                sec_logger.warning(
                    "LOGIN_LOCKOUT email=%s ip=%s",
                    email,
                    request.META.get("REMOTE_ADDR", "?"),
                )
                return Response(
                    {
                        "detail": "Demasiados intentos fallidos. "
                        "Espera unos minutos e intenta de nuevo."
                    },
                    status=status.HTTP_429_TOO_MANY_REQUESTS,
                )

        try:
            serializer = LoginSerializer(data=request.data, context={"request": request})
            serializer.is_valid(raise_exception=True)
        except AuthenticationFailed:
            sec_logger.warning(
                "LOGIN_FAILED email=%s ip=%s",
                email,
                request.META.get("REMOTE_ADDR", "?"),
            )
            if lock_key:
                failures = cache.get(lock_key, 0) + 1
                cache.set(lock_key, failures, timeout=settings.LOGIN_LOCKOUT_MINUTES * 60)
            raise

        if lock_key:
            cache.delete(lock_key)
        user = serializer.validated_data["user"]
        sec_logger.info(
            "LOGIN_SUCCESS user=%s ip=%s",
            user.id,
            request.META.get("REMOTE_ADDR", "?"),
        )

        refresh = RefreshToken.for_user(user)
        _record_outstanding(user, refresh)
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
        if not _origin_is_allowed(request):
            # CSRF (AUDIT C6): la cookie httpOnly viaja sola en requests
            # cross-site; sin verificar el origen, un formulario malicioso
            # podría forzar una rotación. Se rechaza con el mismo 401 genérico
            # para no revelar por qué.
            logger.warning(
                "REFRESH_ORIGIN_REJECTED origin=%s",
                request.META.get("HTTP_ORIGIN") or request.META.get("HTTP_REFERER"),
            )
            return Response(
                {"detail": "Sesión inválida o expirada."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        cookie_name = settings.SIMPLE_JWT["AUTH_COOKIE"]
        refresh_value = request.COOKIES.get(cookie_name)
        if not refresh_value:
            return Response(
                {"detail": "No hay sesión refrescable."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        try:
            refresh = RefreshToken(refresh_value, verify=False)
            user = User.objects.get(pk=refresh["user_id"])
        except (TokenError, ObjectDoesNotExist, KeyError):
            # Token malformado/indecodificable o usuario inexistente: no es
            # necesariamente reuse, así que NO se revoca la familia.
            return Response(
                {"detail": "Sesión inválida o expirada."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # Reuse-detection (C3): un refresh ya rotado está blacklisted. El
        # atacante pudo conservar copias anteriores de la familia: se revoca
        # TODA la familia para neutralizarlas de golpe. La comprobación es
        # explícita aquí porque el constructor de ``RefreshToken`` (verify=True)
        # ya lanza ``TokenError`` al ver un token blacklisted, antes de que el
        # flujo pudiera entrar en este bloque.
        if BlacklistedToken.objects.filter(token__jti=refresh["jti"]).exists():
            logger.warning("REFRESH_REUSE_DETECTED user=%s", user.id)
            _revoke_refresh_family(user)
            return Response(
                {"detail": "Sesión inválida o expirada."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        try:
            # Valida firma y expiración (ya descartado el blacklist arriba).
            refresh.verify()
        except TokenError:
            # Firma inválida o token expirado: no es reuse (no blacklistado),
            # así que NO se revoca la familia (evita DoS por tokens basura).
            return Response(
                {"detail": "Sesión inválida o expirada."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if not user.is_active:
            # Cuenta desactivada: no debe poder renovar sesiones (A7).
            return Response(
                {"detail": "Sesión inválida o expirada."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if not OutstandingToken.objects.filter(user=user, jti=refresh["jti"]).exists():
            # Reuse-detection (C3): si la familia fue revocada/logout y el
            # OutstandingToken ya no existe, ``blacklist()`` lo recrearía.
            # Rechazar aquí impide revivir un refresh borrado.
            return Response(
                {"detail": "Sesión inválida o expirada."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        refresh.blacklist()
        new_refresh = RefreshToken.for_user(user)
        _record_outstanding(user, new_refresh)
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


class DeleteAccountView(APIView):
    """Agenda la eliminación de la cuenta del usuario autenticado (art. 17).

    Body: ``{ "password": "..." }`` — prueba de identidad obligatoria. Efectos:
        1. ``deletion_scheduled_at = ahora + ACCOUNT_DELETION_GRACE_DAYS días``.
        2. Se revocan TODAS las sesiones (refresh outstanding) y la cookie.
        3. Correo de confirmación (best-effort: un fallo de Brevo no deshace
           el agendado) y notificación in-app.
    Durante la gracia el usuario puede iniciar sesión y cancelar con
    ``POST /api/auth/cancel-account-deletion``; al vencer, la purga borra
    cuenta y datos definitivamente.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request):
        # Lockout propio (mismo patrón AUDIT A1 que LoginView): evitar fuerza
        # bruta sobre la contraseña desde una sesión ya abierta.
        lock_key = _delete_lock_key(request.user)
        if cache.get(lock_key, 0) >= settings.MAX_FAILED_LOGIN_ATTEMPTS:
            sec_logger.warning("DELETE_LOCKOUT user=%s", request.user.pk)
            return Response(
                {
                    "detail": "Demasiados intentos fallidos. "
                    "Espera unos minutos e intenta de nuevo."
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        try:
            serializer = DeleteAccountSerializer(data=request.data, user=request.user)
            serializer.is_valid(raise_exception=True)
        except Exception:
            failures = cache.get(lock_key, 0) + 1
            cache.set(lock_key, failures, timeout=settings.LOGIN_LOCKOUT_MINUTES * 60)
            sec_logger.warning(
                "DELETE_PASSWORD_FAILED user=%s ip=%s",
                request.user.pk,
                request.META.get("REMOTE_ADDR", "?"),
            )
            raise
        cache.delete(lock_key)

        schedule_account_deletion(request.user)
        _revoke_refresh_family(request.user)

        user = request.user
        try:
            send_account_deletion_email(user.email, user.name)
        except Exception:  # noqa: BLE001 - el agendado ya ocurrió; no revertir
            pass
        Notification.objects.create(
            user=user,
            kind="system",
            title="Eliminación de cuenta programada",
            message=(
                "Tu cuenta se eliminará definitivamente en "
                f"{settings.ACCOUNT_DELETION_GRACE_DAYS} días. "
                "Puedes cancelarlo desde tu perfil."
            ),
            extra={"scope": "account_deletion", "action": "scheduled"},
        )

        response = Response(
            {
                "detail": (
                    "Tu cuenta se eliminará en "
                    f"{settings.ACCOUNT_DELETION_GRACE_DAYS} días si no lo "
                    "cancelas. Cerramos todas tus sesiones por seguridad."
                ),
                "deletion_scheduled_at": UserSerializer(user).data["deletion_scheduled_at"],
            },
            status=status.HTTP_200_OK,
        )
        return _clear_refresh_cookie(response)


class CancelAccountDeletionView(APIView):
    """Cancela una eliminación de cuenta pendiente (dentro de la gracia).

    Sin body y sin contraseña: el usuario ya está autenticado con Bearer y la
    operación solo restaura su acceso — nunca lo amplía.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        if not user.deletion_scheduled_at:
            return Response(
                {"detail": "No hay ninguna eliminación pendiente."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        cancel_account_deletion(user)
        try:
            send_account_deletion_cancelled_email(user.email, user.name)
        except Exception:  # noqa: BLE001 - la cancelación ya ocurrió; no revertir
            pass
        return Response(
            {
                "detail": "Eliminación cancelada. Tu cuenta sigue activa.",
                "user": UserSerializer(user).data,
            }
        )


class MeView(APIView):
    """Devuelve el perfil del usuario autenticado (token Bearer)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Purga perezosa (sin cron desplegado): máximo una corrida diaria por
        # instancia; se excluye al usuario del request para no borrarlo a sí
        # mismo en mitad de la respuesta.
        maybe_purge_daily(exclude_user_pk=request.user.pk)
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


class NaviLearningConsentView(APIView):
    """Estado y control del consentimiento de aprendizaje de Navi.

    GET: devuelve ``{ mode, consent_at }``.  Si ``consent_at`` es null, el
    usuario nunca ha sido preguntado (el frontend debe mostrar el modal).
    POST: acepta ``{ "mode": "full"|"manual"|"none" }`` y actualiza el perfil.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        return Response(
            {
                "mode": user.navi_learning_mode,
                "consent_at": user.navi_learning_consent_at,
            }
        )

    def post(self, request):
        from apps.accounts.serializers import NaviLearningConsentSerializer

        serializer = NaviLearningConsentSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        user = request.user
        return Response(
            {
                "mode": user.navi_learning_mode,
                "consent_at": user.navi_learning_consent_at,
            },
            status=status.HTTP_200_OK,
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