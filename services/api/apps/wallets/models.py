"""models — Modelo ``Wallet``: billetera de dinero con saldo.

El saldo se mantiene mediante ``services.adjust_balance`` (siempre dentro de
una transacción de BD) y nunca se calcula sumando operaciones al vuelo: es un
dato materializado que se ajusta de forma atómica (ver ADR-08 y Riesgo R9).
"""

from __future__ import annotations

from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models

from apps.core.currency import CURRENCY_CHOICES, MONEY_DECIMALS
from apps.core.models import OwnedModel

#: Tipos de billetera soportados en el MVP.
WALLET_TYPES = [
    ("cash", "Efectivo"),
    ("bank", "Banco"),
    ("saving", "Ahorro"),
    ("other", "Otro"),
]

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
        help_text="Color identificador (hex) que armoniza con el tema glass.",
    )

    class Meta:
        verbose_name = "Billetera"
        verbose_name_plural = "Billeteras"
        ordering = ["created_at"]
        constraints = [
            # Un usuario no puede tener dos billeteras con el mismo nombre.
            models.UniqueConstraint(fields=["user", "name"], name="uniq_wallet_name_per_user")
        ]

    def __str__(self) -> str:
        """Representación: nombre (moneda)."""
        return f"{self.name} ({self.currency})"