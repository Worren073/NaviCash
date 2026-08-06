"""serializers — Serializers de ``accounts``.

Incluyen la serialización del usuario (perfil), el registro (crea usuario +
token de verificación + envía el correo) y la verificación de email.
"""

from __future__ import annotations

import re

from django.conf import settings
from django.contrib.auth import authenticate
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed

from apps.accounts.captcha import verify_turnstile
from apps.accounts.emails import send_verification_email
from apps.accounts.models import EmailVerification, User
from apps.core.currency import CURRENCY_CHOICES
from django.core.validators import validate_email

#: Teléfono aceptable: opcional '+', dígitos y separadores comunes.
PHONE_RE = re.compile(r"^\+?[\d\s()-]{7,20}$")


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
        """Comprueba que el email no esté ya registrado."""
        validate_email(value)
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("Ya existe una cuenta con este correo.")
        return value.lower()

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
        """Fuerza contraseña: ≥ 8 caracteres, al menos una letra y un número."""
        if len(value) < 8:
            raise serializers.ValidationError("La contraseña debe tener al menos 8 caracteres.")
        if not re.search(r"[A-Za-záéíóúÁÉÍÓÚñü]", value):
            raise serializers.ValidationError("La contraseña debe incluir al menos una letra.")
        if not re.search(r"\d", value):
            raise serializers.ValidationError("La contraseña debe incluir al menos un número.")
        return value

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
        """Crea el usuario inactivo y lanza el flujo de verificación."""
        user = User.objects.create_user(
            email=validated_data["email"],
            password=validated_data["password"],
            first_name=validated_data.get("first_name", ""),
            last_name=validated_data.get("last_name", ""),
            phone=validated_data.get("phone", ""),
            base_currency=validated_data.get("base_currency", "USD"),
            is_active=False,  # Se activa al verificar el email.
            accepted_terms_at=timezone.now(),
            accepted_terms_version=settings.TERMS_VERSION,
        )
        verification = EmailVerification.create_for_user(user)
        send_verification_email(user.email, verification.token, user.name)
        return user


class VerifyEmailSerializer(serializers.Serializer):
    """Activa la cuenta mediante el token enviado por correo."""

    token = serializers.CharField(max_length=64, write_only=True)

    def validate_token(self, value: str) -> str:
        """Busca el token y comprueba validez (no usado y no caducado)."""
        try:
            verification = EmailVerification.objects.select_related("user").get(token=value)
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
            token=self.validated_data["token"]
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