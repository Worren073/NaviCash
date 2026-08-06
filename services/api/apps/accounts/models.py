"""models — Modelos de ``accounts``: User y EmailVerification.

``User`` es el modelo de autenticación del proyecto (``AUTH_USER_MODEL``).
Los usuarios se registran con email+contraseña y permanecen inactivos hasta
verificar su email (ADR-06).

La "moneda base" elegida en el onboarding y la regla global de recordatorios
viven en este modelo (ver PLAN: RF-04/05/25, ADR-10).
"""

from __future__ import annotations

import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.core.validators import EmailValidator
from django.db import models
from django.utils import timezone

from apps.accounts.managers import UserManager
from apps.core.currency import CURRENCY_CHOICES


class User(AbstractBaseUser, PermissionsMixin):
    """Usuario de NaviCash identificado por email.

    Campos:
        email: identificador único (normalizado a minúsculas).
        first_name / last_name: nombre y apellido del usuario (opcionales);
            ``name`` (propiedad) devuelve la forma legible.
        phone: teléfono opcional (formato libre sugerido E.164).
        accepted_terms_at / accepted_terms_version: registro de la aceptación
            de los términos de servicio al registrarse.
        base_currency: moneda base de visualización elegida en el onboarding
                       (ADR-10). La API devuelve los totales convertidos a USD
                       con la tasa oficial; la UI formatea según esta moneda.
        language: idioma de la interfaz (el MVP soporta español latino).
        timezone: zona horaria del usuario (los vencimientos "retrasado" y los
                  recordatorios se calculan en esta zona — ver Riesgo R8).
        reminder_days: regla global de recordatorio: avisar N días antes del
                       vencimiento (ADR-09).
        is_active: False hasta que se verifique el email (ADR-06).
    """

    email = models.EmailField(
        unique=True,
        max_length=255,
        validators=[EmailValidator()],
        verbose_name="Correo electrónico",
        help_text="Identificador único; se normaliza a minúsculas.",
    )
    first_name = models.CharField(max_length=60, blank=True, verbose_name="Nombre")
    last_name = models.CharField(max_length=60, blank=True, verbose_name="Apellido")
    phone = models.CharField(
        max_length=24,
        blank=True,
        verbose_name="Teléfono",
        help_text="Ej. +58 424 123 4567.",
    )
    accepted_terms_at = models.DateTimeField(
        null=True, blank=True, verbose_name="Términos aceptados el"
    )
    accepted_terms_version = models.CharField(
        max_length=20, blank=True, default="", verbose_name="Versión de términos"
    )
    base_currency = models.CharField(
        max_length=3,
        choices=CURRENCY_CHOICES,
        default="USD",
        verbose_name="Moneda base",
        help_text="Moneda con la que el usuario quiere ver sus finanzas (ADR-10).",
    )
    language = models.CharField(
        max_length=10, choices=[("es", "Español")], default="es", verbose_name="Idioma"
    )
    timezone_name = models.CharField(
        max_length=64,
        default="America/Caracas",
        verbose_name="Zona horaria",
        help_text="Ej. America/Caracas (UTC-4) para Venezuela.",
    )
    reminder_days = models.PositiveSmallIntegerField(
        default=3,
        verbose_name="Días de recordatorio",
        help_text="Regla global: avisar pagos que vencen en N días (ADR-09).",
    )
    is_active = models.BooleanField(
        default=False,
        verbose_name="Activo",
        help_text="Se activa tras verificar el email.",
    )
    is_staff = models.BooleanField(default=False, verbose_name="Staff")
    date_joined = models.DateTimeField(default=timezone.now, verbose_name="Registrado el")

    objects = UserManager()

    USERNAME_FIELD = "email"  # Login con email (no username).
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = "Usuario"
        verbose_name_plural = "Usuarios"
        ordering = ["-date_joined"]

    def __str__(self) -> str:
        """Representación legible: email o nombre + email."""
        return self.name or self.email

    @property
    def is_verified(self) -> bool:
        """True si el usuario ya confirmó su email (equivalente a is_active)."""
        return self.is_active

    @property
    def name(self) -> str:
        """Nombre completo legible (nombre + apellido), o el email si está vacío."""
        return f"{self.first_name} {self.last_name}".strip() or self.email

    def full_name(self) -> str:
        """Alias legible del nombre del usuario."""
        return self.name


class EmailVerification(models.Model):
    """Token único de verificación de email.

    - ``token``: string aleatorio seguro, de un solo uso.
    - ``expires_at``: caducidad (por defecto 24 h, configurable).
    - Al verificar, se activa ``user.is_active`` y se marca el token como usado.
    """

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="verification", verbose_name="Usuario"
    )
    token = models.CharField(max_length=64, unique=True, verbose_name="Token")
    expires_at = models.DateTimeField(verbose_name="Expira el")
    used = models.BooleanField(default=False, verbose_name="Usado")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Creado el")

    class Meta:
        verbose_name = "Verificación de email"
        verbose_name_plural = "Verificaciones de email"

    def __str__(self) -> str:
        """Representación: email del usuario y si está usado."""
        return f"Verificación de {self.user.email} (usado={self.used})"

    @classmethod
    def create_for_user(cls, user: User) -> "EmailVerification":
        """Crea (o renueva) el token de verificación del usuario.

        Args:
            user: usuario recién registrado (is_active=False).

        Returns:
            Instancia de ``EmailVerification`` persistida con token fresco.
        """
        hours = getattr(settings, "VERIFICATION_TOKEN_HOURS", 24)
        cls.objects.filter(user=user).delete()
        return cls.objects.create(
            user=user,
            token=secrets.token_urlsafe(32),
            expires_at=timezone.now() + timedelta(hours=hours),
        )

    def is_valid(self) -> bool:
        """Comprueba que el token no esté usado ni caducado.

        Returns:
            True si puede utilizarse para activar la cuenta.
        """
        return not self.used and self.expires_at > timezone.now()