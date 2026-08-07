"""views — Endpoints de ``accounts``: registro, login, refresh, logout, perfil.

La autenticación usa SimpleJWT con la siguiente división de responsabilidades:
- El **access token** (corto, 15 min) viaja en ``Authorization: Bearer ...``.
- El **refresh token** (largo, 30 días) viaja en una **cookie httpOnly**
  llamada ``refresh_token`` restringida a ``/api/auth/`` (no accesible a JS,
  protegiendo contra XSS — ver RNF-01).
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import User
from apps.accounts.serializers import (
    LoginSerializer,
    RegisterSerializer,
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


class RegisterView(APIView):
    """Crea una cuenta nueva y envía el correo de verificación.

    Respuesta 201 con ``{detail, token_de_verificacion?}``.
    En modo debug se devuelve ``debug_token`` para facilitar las pruebas locales
    (en producción ese campo no existe).
    """

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        payload = {"detail": "Cuenta creada. Revisa tu correo para verificar el email."}
        if settings.DEBUG:
            verification = user.verification
            payload["debug_token"] = verification.token
        return Response(payload, status=status.HTTP_201_CREATED)


class LoginView(APIView):
    """Inicia sesión con email + contraseña.

    Comportamiento:
        - Devuelve ``access`` en el body (corto).
        - Guarda ``refresh_token`` en cookie httpOnly.
        - Si la cuenta no está verificada responde 401 con code ``not_verified``.
    """

    permission_classes = [AllowAny]

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

    Debido a ``ROTATE_REFRESH_TOKENS=True``, la rotación emite un nuevo refresh
    y añade el anterior al blacklist. Requiere cookie válida.
    """

    permission_classes = [AllowAny]

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
            user = User.objects.get(pk=refresh["user_id"])
        except (ObjectDoesNotExist, Exception):
            return Response(
                {"detail": "Sesión inválida o expirada."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        new_refresh = RefreshToken.for_user(user)
        response = Response({"access": str(new_refresh.access_token)}, status=status.HTTP_200_OK)
        return _set_refresh_cookie(response, new_refresh)


class LogoutView(APIView):
    """Cierra sesión: añade el refresh a la blacklist y borra la cookie.

    Requiere estar autenticado (tener un access valido). El refresh con el que
    se creó la cookie se invalida para que no pueda reutilizarse.
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
        response = Response({"detail": "Sesión cerrada."}, status=status.HTTP_200_OK)
        return _clear_refresh_cookie(response)


class VerifyEmailView(APIView):
    """Activa la cuenta verificando el token del correo.

    Body: ``{ "token": "..." }``. Respuesta 200 con el perfil activo.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = VerifyEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response({"detail": "Cuenta verificada.", "user": UserSerializer(user).data})


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