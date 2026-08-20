"""models — Modelo ``Wallet``: billetera de dinero con saldo.

El saldo se mantiene mediante ``services.adjust_balance`` (siempre dentro de
una transacción de BD) y nunca se calcula sumando operaciones al vuelo: es un
dato materializado que se ajusta de forma atómica (ver ADR-08 y Riesgo R9).
"""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from apps.core.currency import CURRENCY_CHOICES, MONEY_DECIMALS
from apps.core.exceptions import BusinessRuleError
from apps.core.models import OwnedModel

#: Tipos de billetera soportados en el MVP.
WALLET_TYPES = [
    ("cash", "Efectivo"),
    ("bank", "Banco"),
    ("saving", "Ahorro"),
    ("other", "Otro"),
]


class WalletManager(models.Manager):
    """Manager por defecto: excluye billeteras ocultas (soft-delete, C4).

    ``Wallet.all_objects`` expone el total (administración/auditoría); la API
    pública solo ve ``is_deleted=False``.
    """

    def get_queryset(self):
        """Solo billeteras no borradas."""
        return super().get_queryset().filter(is_deleted=False)

#: Colores sugeridos para la billetera (paleta que armoniza con el glass).
WALLET_COLORS = [
    "#006a61",  # teal (primario)
    "#2563eb",  # azul
    "#7c3aed",  # violeta
    "#0891b2",  # cian
    "#16a34a",  # verde
    "#d97706",  # ámbar
    "#ea580c",  # naranja
    "#e11d48",  # rosa
    "#db2777",  # fucsia
    "#475569",  # slate
]


class Wallet(OwnedModel):
    """Una billetera de dinero del usuario.

    Campos:
        name: nombre visible (ej. "Efectivo Bs").
        currency: moneda de la billetera (ISO 4217).
        saldo: saldo actual materializado (Decimal, 2 decimales, >= 0).
        tipo: efectivo / banco / otro.
    """

    name = models.CharField(max_length=80, verbose_name="Nombre")
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, verbose_name="Moneda")
    saldo = models.DecimalField(
        max_digits=20,
        decimal_places=MONEY_DECIMALS,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0"))],
        verbose_name="Saldo",
help_text="Saldo actual; se ajusta automáticamente con los pagos y manualmente por el usuario.",
    )
    tipo = models.CharField(max_length=10, choices=WALLET_TYPES, default="cash", verbose_name="Tipo")
    color = models.CharField(
        max_length=9,
        default="#006a61",
        blank=True,
        verbose_name="Color",
        help_text="Color identificador (hex) que armoniza con el glass.",
    )
    is_deleted = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name="Oculta",
        help_text="Soft-delete (C4): la billetera se oculta de la API pero conserva su historial.",
    )

    objects = WalletManager()
    all_objects = models.Manager()

    class Meta:
        verbose_name = "Billetera"
        verbose_name_plural = "Billeteras"
        ordering = ["created_at"]
        default_manager_name = "objects"
        indexes = [
            # A9: listado del usuario (el manager filtra por is_deleted).
            models.Index(fields=["user", "is_deleted"]),
            models.Index(fields=["user", "created_at"]),
        ]
        constraints = [
            # Un usuario no puede tener dos billeteras con el mismo nombre.
            models.UniqueConstraint(
                fields=["user", "name"],
                name="uniq_wallet_name_per_user",
                condition=models.Q(is_deleted=False),
            ),
            # Respaldo a nivel de BD del invariante del dominio (C1/A10):
            # el saldo jamás puede quedar negativo, aunque una carrera de
            # escrituras escape a la validación de ``adjust_balance``.
            models.CheckConstraint(
                condition=models.Q(saldo__gte=Decimal("0")),
                name="wallet_saldo_gte_0",
                violation_error_message="El saldo no puede ser negativo.",
            ),
        ]

    def __str__(self) -> str:
        """Representación: nombre (moneda)."""
        return f"{self.name} ({self.currency})"

    def delete(self, using=None, keep_parents=False):
        """Soft-delete (C4): oculta la billetera, nunca la borra del historial.

        Se bloquea si la billetera aún tiene saldo: ocultar dinero congelaría
        fondos vivos sin posibilidad de auditar su destino. El usuario debe
        dejarla en 0 (ajuste/transferencia) antes de ocultarla.
        """
        if self.saldo > 0:
            raise BusinessRuleError(
                f"No puedes eliminar '{self.name}': aún tiene saldo "
                f"({self.saldo:.2f} {self.currency})."
            )
        self.is_deleted = True
        self.save(update_fields=["is_deleted", "updated_at"])


class BalanceAuditLog(models.Model):
    """Pista de auditoría de cada ajuste de saldo (C4).

    Se escribe DENTRO de la misma transacción de ``adjust_balance`` (wallets/
    services.py): por cada movimiento de una billetera queda quién/cuándo
    (``created_at``), el delta aplicado y el saldo resultante. ``wallet`` usa
    PROTECT: no se puede borrar físicamente una billetera con log de auditoría.
    """

    wallet = models.ForeignKey(
        Wallet,
        on_delete=models.PROTECT,
        related_name="audit_logs",
        verbose_name="Billetera",
    )
    delta = models.DecimalField(
        max_digits=20,
        decimal_places=MONEY_DECIMALS,
        verbose_name="Variación",
        help_text="Delta aplicado (positivo suma, negativo resta).",
    )
    balance_after = models.DecimalField(
        max_digits=20,
        decimal_places=MONEY_DECIMALS,
        verbose_name="Saldo resultante",
    )
    reason = models.CharField(
        max_length=120,
        blank=True,
        default="",
        verbose_name="Motivo",
        help_text="Ej: ajuste_manual, transaction-<id>, transfer-in/out.",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="balance_audit_logs",
        verbose_name="Usuario",
        help_text="Dueño de la billetera al momento del ajuste.",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Creado el")

    class Meta:
        verbose_name = "Registro de auditoría de saldo"
        verbose_name_plural = "Registros de auditoría de saldos"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["wallet", "-created_at"]),
        ]

    def __str__(self) -> str:
        """Representación: delta sobre saldo en la billetera."""
        return f"{self.delta} → {self.balance_after} ({self.wallet_id})"