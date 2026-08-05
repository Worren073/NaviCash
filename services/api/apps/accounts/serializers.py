"""serializers — Serializers de ``accounts``.

Incluyen la serialización del usuario (perfil), el registro (crea usuario +
token de verificación + envía el correo) y la verificación de email.
"""

from __future__ import annotations

from django.contrib.auth import authenticate
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed

from apps.accounts.emails import send_verification_email
from apps.accounts.models import EmailVerification, User
from apps.core.currency import CURRENCY_CHOICES, is_valid_amount
from apps.core.exceptions import BusinessRuleError
from django.core.validators import validate_email


class UserSerializer(serializers.ModelSerializer):
    """Serializador público del perfil de usuario (GET /api/auth/me)."""

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "name",
            "base_currency",
            "language",
            "timezone_name",
            "reminder_days",
            "is_active",
            "date_joined",
        ]
        read_only_fields = ["id", "email", "is_active", "date_joined"]


class UserUpdateSerializer(serializers.ModelSerializer):
    """Edición de perfil (PATCH /api/auth/me, RF-05)."""

    class Meta:
        model = User
        fields = ["name", "base_currency", "language", "timezone_name", "reminder_days"]
        extra_kwargs = {
            "reminder_days": {"min_value": 0, "max_value": 30},
        }


class RegisterSerializer(serializers.Serializer):
    """Valida y crea un nuevo usuario con verificación de email.

    Campos aceptados (JSON):
        email, password, name (opcional), base_currency (opcional).

    Efectos:
        1. Crea el usuario con ``is_active=False`` (ADR-06).
        2. Genera el token de verificación (caduca en 24 h).
        3. Envía el correo de confirmación.
    """

    email = serializers.EmailField(max_length=255)
    password = serializers.CharField(
        min_length=8,
        max_length=128,
        write_only=True,
        help_text="Mínimo 8 caracteres.",
    )
    name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    base_currency = serializers.ChoiceField(
        choices=CURRENCY_CHOICES, required=False, default="USD"
    )

    def validate_email(self, value: str) -> str:
        """Comprueba que el email no esté ya registrado."""
        validate_email(value)
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("Ya existe una cuenta con este correo.")
        return value.lower()

    def create(self, validated_data: dict) -> User:
        """Crea el usuario inactivo y lanza el flujo de verificación."""
        user = User.objects.create_user(
            email=validated_data["email"],
            password=validated_data["password"],
            name=validated_data.get("name", ""),
            base_currency=validated_data.get("base_currency", "USD"),
            is_active=False,  # Se activa al verificar el email.
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