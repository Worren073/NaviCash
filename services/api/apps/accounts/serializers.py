"""serializers — Serializers de ``accounts``.

Incluyen la serialización del usuario (perfil), el registro (crea usuario +
token de verificación + envía el correo) y la verificación de email.
"""

from __future__ import annotations

import re

from django.conf import settings
from django.contrib.auth import authenticate, password_validation
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed

from apps.accounts.captcha import verify_turnstile
from apps.accounts.emails import send_verification_email
from apps.accounts.models import EmailVerification, LegalDocument, PasswordResetToken, User
from apps.core.currency import CURRENCY_CHOICES
from django.core.validators import validate_email

#: Teléfono aceptable: opcional '+', dígitos y separadores comunes.
PHONE_RE = re.compile(r"^\+?[\d\s()-]{7,20}$")


def validate_password_strength(value: str, user=None) -> str:
    """Fuerza contraseña: ≥ 8 caracteres, una letra, un número y los
    validadores de Django configurados en ``settings.AUTH_PASSWORD_VALIDATORS``
    (similitud con atributos del usuario, común, numérica — AUDIT A5).

    Regla compartida por registro y recuperación/cambio de contraseña.
    """
    if len(value) < 8:
        raise serializers.ValidationError("La contraseña debe tener al menos 8 caracteres.")
    if not re.search(r"[A-Za-záéíóúÁÉÍÓÚñü]", value):
        raise serializers.ValidationError("La contraseña debe incluir al menos una letra.")
    if not re.search(r"\d", value):
        raise serializers.ValidationError("La contraseña debe incluir al menos un número.")
    # AUDIT A5: en producción se ejecutan los validators de Django; en tests
    # ``AUTH_PASSWORD_VALIDATORS`` está vacío (ver config/test_settings.py).
    password_validation.validate_password(value, user=user)
    return value


class UserSerializer(serializers.ModelSerializer):
    """Serializador público del perfil de usuario (GET /api/auth/me)."""

    name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "name",
            "first_name",
            "last_name",
            "phone",
            "base_currency",
            "language",
            "timezone_name",
            "reminder_days",
            "is_onboarded",
            "is_active",
            "date_joined",
        ]
        read_only_fields = ["id", "email", "name", "is_active", "date_joined"]

    def get_name(self, obj: User) -> str:
        """Nombre completo legible (o email)."""
        return obj.name


class UserUpdateSerializer(serializers.ModelSerializer):
    """Edición de perfil (PATCH /api/auth/me, RF-05)."""

    class Meta:
        model = User
        fields = [
            "first_name",
            "last_name",
            "phone",
            "base_currency",
            "language",
            "timezone_name",
            "reminder_days",
            "is_onboarded",
        ]
        extra_kwargs = {
            "reminder_days": {"min_value": 0, "max_value": 30},
        }

    def validate_phone(self, value: str) -> str:
        """Valida el formato del teléfono si viene informado."""
        if value and not PHONE_RE.fullmatch(value):
            raise serializers.ValidationError(
                "Ingresa un teléfono válido, p. ej. +58 424 123 4567."
            )
        return value


class RegisterSerializer(serializers.Serializer):
    """Valida y crea un nuevo usuario con verificación de email.

    Campos aceptados (JSON):
        email, password, first_name, last_name (opcionales), phone (opcional),
        base_currency (opcional), accepted_terms (obligatorio true),
        captcha_token (obligatorio si el CAPTCHA está activo).

    Efectos:
        1. Valida el CAPTCHA (Turnstile) si está activo.
        2. Crea el usuario con ``is_active=False`` (ADR-06) y graba la
           aceptación de los términos.
        3. Genera el token de verificación (caduca en 24 h).
        4. Envía el correo de confirmación.
    """

    email = serializers.EmailField(max_length=255)
    password = serializers.CharField(
        min_length=8,
        max_length=128,
        write_only=True,
        help_text="Mínimo 8 caracteres, con letras y números.",
    )
    first_name = serializers.CharField(max_length=60, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=60, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=24, required=False, allow_blank=True)
    base_currency = serializers.ChoiceField(
        choices=CURRENCY_CHOICES, required=False, default="USD"
    )
    accepted_terms = serializers.BooleanField(default=False)
    captcha_token = serializers.CharField(
        required=False, allow_blank=True, write_only=True
    )

    def validate_email(self, value: str) -> str:
        """Comprueba que el email no esté ya registrado.

        Anti-enumeración (AUDIT B5): en vez de fallar con "ya existe", se
        marca la duplicidad para que la vista responda igual que el éxito
        (mensaje genérico). El flag queda en ``email_already_registered``.
        """
        validate_email(value)
        self._email_exists = User.objects.filter(email__iexact=value).exists()
        return value.lower()

    @property
    def email_already_registered(self) -> bool:
        """True si el email del payload ya pertenece a otra cuenta (B5)."""
        return bool(getattr(self, "_email_exists", False))

    def validate_first_name(self, value: str) -> str:
        """El nombre (si viene) solo admite letras y espacios."""
        if value and not re.match(r"^[A-Za-zÁÉÍÓÚÑÜáéíóúñü' ]+$", value):
            raise serializers.ValidationError("El nombre solo puede contener letras y espacios.")
        return value

    def validate_last_name(self, value: str) -> str:
        """El apellido (si viene) solo admite letras y espacios."""
        if value and not re.match(r"^[A-Za-zÁÉÍÓÚÑÜáéíóúñü' ]+$", value):
            raise serializers.ValidationError("El apellido solo puede contener letras y espacios.")
        return value

    def validate_phone(self, value: str) -> str:
        """Teléfono opcional pero con formato válido si se informa."""
        if value and not PHONE_RE.fullmatch(value):
            raise serializers.ValidationError(
                "Ingresa un teléfono válido, p. ej. +58 424 123 4567."
            )
        return value

    def validate_password(self, value: str) -> str:
        """Aplica la regla común de fortaleza de contraseña + validators de Django.

        El usuario aún no existe al registrar, así que la validación de
        similitud (UserAttributeSimilarityValidator) se omite para el registro
        (no hay atributos previos que comparar).
        """
        return validate_password_strength(value)

    def validate_accepted_terms(self, value: bool) -> bool:
        """La aceptación de los términos es obligatoria."""
        if value is not True:
            raise serializers.ValidationError("Debes aceptar los términos y condiciones.")
        return value

    def validate(self, attrs: dict) -> dict:
        """Verifica el CAPTCHA (si está activo) antes de crear el usuario."""
        if not verify_turnstile(attrs.get("captcha_token", "")):
            raise serializers.ValidationError(
                {"captcha_token": "No se pudo verificar que eres humano. Intenta de nuevo."}
            )
        return attrs

    def create(self, validated_data: dict) -> User:
        """Crea el usuario y, según la configuración, lanza la verificación.

        Si ``EMAIL_VERIFICATION_REQUIRED`` es True (default) el usuario nace
        inactivo y se envía el correo de confirmación. Si es False, nace activo
        sin enviar correo (modo sin verificación).
        """
        verification_required = settings.EMAIL_VERIFICATION_REQUIRED
        user = User.objects.create_user(
            email=validated_data["email"],
            password=validated_data["password"],
            first_name=validated_data.get("first_name", ""),
            last_name=validated_data.get("last_name", ""),
            phone=validated_data.get("phone", ""),
            base_currency=validated_data.get("base_currency", "USD"),
            is_active=not verification_required,  # Se activa al verificar el email.
            accepted_terms_at=timezone.now(),
            accepted_terms_version=settings.TERMS_VERSION,
        )
        if verification_required:
            verification = EmailVerification.create_for_user(user)
            send_verification_email(user.email, verification.token, user.name)
        return user


class VerifyEmailSerializer(serializers.Serializer):
    """Activa la cuenta mediante el token enviado por correo."""

    token = serializers.CharField(max_length=64, write_only=True)

    def validate_token(self, value: str) -> str:
        """Busca el token por su hash y comprueba validez (no usado ni caduco)."""
        try:
            verification = EmailVerification.objects.select_related("user").get(
                token=EmailVerification.hash_token(value)
            )
        except EmailVerification.DoesNotExist:
            raise serializers.ValidationError("Token inválido.")
        if not verification.is_valid():
            raise serializers.ValidationError("Token caducado o ya utilizado.")
        return value

    def save(self) -> User:
        """Marca el token como usado y activa la cuenta.

        Returns:
            El usuario recién verificado (is_active=True).
        """
        verification = EmailVerification.objects.select_related("user").get(
            token=EmailVerification.hash_token(self.validated_data["token"])
        )
        verification.used = True
        verification.save(update_fields=["used"])
        user = verification.user
        if not user.is_active:
            user.is_active = True
            user.save(update_fields=["is_active"])
        return user


class LoginSerializer(serializers.Serializer):
    """Autentica con email + contraseña y devuelve el usuario.

    Se usa desde ``LoginView`` para emitir los tokens JWT.
    """

    email = serializers.EmailField(max_length=255)
    password = serializers.CharField(max_length=128, write_only=True)

    def validate(self, attrs: dict) -> dict:
        """Comprueba credenciales y que la cuenta esté verificada."""
        user = authenticate(
            request=self.context.get("request"),
            username=attrs["email"].lower(),
            password=attrs["password"],
        )
        if user is None:
            raise AuthenticationFailed("Correo o contraseña incorrectos.")
        if not user.is_active:
            raise AuthenticationFailed(
                "Cuenta sin verificar. Revisa tu correo para activarla.",
                code="not_verified",
            )
        attrs["user"] = user
        return attrs


class ForgotPasswordSerializer(serializers.Serializer):
    """Solicita el enlace de recuperación de contraseña.

    Solo valida el formato del email: la existencia de la cuenta NO se expone
    (la vista responde siempre lo mismo — AUDIT B5).
    """

    email = serializers.EmailField(max_length=255)

    def validate_email(self, value: str) -> str:
        """Normaliza el email a minúsculas."""
        return value.lower()


class ResetPasswordSerializer(serializers.Serializer):
    """Restablece la contraseña con el token del correo (one-time, M13)."""

    token = serializers.CharField(max_length=64, write_only=True)
    password = serializers.CharField(max_length=128, write_only=True)

    def validate_token(self, value: str) -> str:
        """Busca el token por su hash y comprueba validez (no usado ni caduco)."""
        try:
            reset = PasswordResetToken.objects.select_related("user").get(
                token=PasswordResetToken.hash_token(value)
            )
        except PasswordResetToken.DoesNotExist:
            raise serializers.ValidationError("Enlace inválido o ya utilizado.")
        if not reset.is_valid():
            raise serializers.ValidationError("El enlace caducó o ya fue utilizado.")
        # Se recuerda el usuario para validar la nueva clave contra sus
        # atributos (similitud) y no permitir claves iguales a sus datos.
        self._reset_user = reset.user
        return value

    def validate_password(self, value: str) -> str:
        """Aplica la regla común de fortaleza + validators de Django."""
        return validate_password_strength(value, user=getattr(self, "_reset_user", None))

    def save(self) -> User:
        """Cambia la contraseña e invalida el token (one-time).

        No autentica al usuario: tras el reset debe iniciar sesión con la
        nueva contraseña (la vista revoca su familia de refresh).

        Returns:
            El usuario con la contraseña actualizada.
        """
        reset = PasswordResetToken.objects.select_related("user").get(
            token=PasswordResetToken.hash_token(self.validated_data["token"])
        )
        user = reset.user
        user.set_password(self.validated_data["password"])
        user.save(update_fields=["password"])
        reset.used = True
        reset.save(update_fields=["used"])
        return user


class ChangePasswordSerializer(serializers.Serializer):
    """Cambia la contraseña del usuario autenticado (verifica la actual)."""

    current_password = serializers.CharField(max_length=128, write_only=True)
    new_password = serializers.CharField(max_length=128, write_only=True)

    def __init__(self, *args, **kwargs):
        """Acepta el usuario autenticado vía ``user=`` para verificar la actual."""
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

    def validate_current_password(self, value: str) -> str:
        """Comprueba que la contraseña actual sea correcta."""
        if self.user is None or not self.user.check_password(value):
            raise serializers.ValidationError("La contraseña actual es incorrecta.")
        return value

    def validate_new_password(self, value: str) -> str:
        """Aplica la regla común de fortaleza + validators de Django (con el
        usuario autenticado, para que la clave no se parezca a sus datos)."""
        return validate_password_strength(value, user=self.user)

    def validate(self, attrs: dict) -> dict:
        """La nueva contraseña debe diferir de la actual."""
        if attrs["current_password"] == attrs["new_password"]:
            raise serializers.ValidationError(
                "La nueva contraseña debe ser distinta de la actual."
            )
        return attrs

    def save(self) -> User:
        """Cambia la contraseña del usuario (la vista revoca la familia JWT)."""
        self.user.set_password(self.validated_data["new_password"])
        self.user.save(update_fields=["password"])
        return self.user


class LegalDocumentSerializer(serializers.ModelSerializer):
    """Serializador de documentos legales (términos, privacidad)."""

    class Meta:
        model = LegalDocument
        fields = [
            "id",
            "doc_type",
            "version",
            "title",
            "content",
            "is_active",
            "created_at",
            "updated_at",
            "effective_at",
        ]
        read_only_fields = fields


class AcceptTermsSerializer(serializers.Serializer):
    """Registra la (re)aceptación de los Términos y Condiciones vigentes.

    Status 400 si el usuario todavía no ha verificado su correo (``is_active``
    False). No se recibe ningún dato del cliente: la aceptación se repliega
    siempre sobre la versión activa del servidor (``settings.TERMS_VERSION``).
    """

    accepted = serializers.BooleanField(required=True)

    def validate_accepted(self, value: bool) -> bool:
        """La (re)aceptación debe llegar explícitamente en ``True``."""
        if value is not True:
            raise serializers.ValidationError("Debes aceptar los términos y condiciones.")
        return value

    def validate(self, attrs: dict) -> dict:
        """Requiere una cuenta activa; las cuentas sin email verificado no pueden aceptar."""
        user = self.context.get("request").user if self.context else None
        if user is not None and not user.is_active:
            raise serializers.ValidationError(
                {"detail": "Debes verificar tu correo electrónico para continuar."}
            )
        return attrs

    def save(self, **kwargs):
        """Fija la fecha y versión de aceptación con la versión vigente del servidor."""
        user = self.context["request"].user
        user.accepted_terms_at = timezone.now()
        user.accepted_terms_version = settings.TERMS_VERSION
        user.save(update_fields=["accepted_terms_at", "accepted_terms_version"])
        return user