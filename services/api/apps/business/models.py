"""models — Modelo ``Business``: negocio del usuario con cuenta propia.

Los fondos del negocio viven en su billetera (``Wallet.tipo == "business"``),
ligada por el OneToOne ``Wallet.business`` (la relación inversa se expone como
``business.wallet``). El saldo se gestiona con el MISMO motor de
``wallets.services.adjust_balance`` (ADR-08); aquí solo se modela la identidad
del negocio (nombre y moneda) y el invariante de "un negocio por usuario".
"""

from __future__ import annotations

from django.db import models

from apps.core.currency import CURRENCY_CHOICES
from apps.core.models import OwnedModel


class Business(OwnedModel):
    """Un negocio por usuario (MVP).

    El modelo no declara la billetera como campo propio: la relación inversa
    del OneToOne ``Wallet.business`` permite acceder a ``business.wallet`` y
    filtrar con ``wallet__*`` (ej. scopes personal/business).
    """

    name = models.CharField(max_length=80, verbose_name="Nombre")
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, verbose_name="Moneda")

    class Meta:
        verbose_name = "Negocio"
        verbose_name_plural = "Negocios"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user"]),
        ]
        constraints = [
            # Un usuario solo puede tener un negocio en el MVP.
            models.UniqueConstraint(fields=["user"], name="uniq_business_per_user"),
        ]

    def __str__(self) -> str:
        """Representación: nombre (moneda)."""
        return f"{self.name} ({self.currency})"