"""models — Modelo ``Business``: negocio del usuario con cuenta propia.

Los fondos del negocio viven en sus billeteras (``Wallet.tipo == "business"``),
ligadas por la FK ``Wallet.business``: una cuenta ``primary`` (moneda base del
negocio) y una ``secondary`` (la otra moneda, VES/USD). El saldo se gestiona con
el MISMO motor de ``wallets.services.adjust_balance`` (ADR-08); aquí solo se
modela la identidad del negocio (nombre y moneda) y el invariante de "un negocio
por usuario".
"""

from __future__ import annotations

from django.db import models

from apps.core.currency import BUSINESS_CURRENCY_CHOICES
from apps.core.models import OwnedModel


class Business(OwnedModel):
    """Un negocio por usuario (MVP).

    La relación inversa de la FK ``Wallet.business`` se expone como
    ``business.wallets`` (ambas cuentas) y por comodidad como ``business.wallet``
    (la principal) y ``business.secondary_wallet``.
    """

    name = models.CharField(max_length=80, verbose_name="Nombre")
    currency = models.CharField(
        max_length=3, choices=BUSINESS_CURRENCY_CHOICES, verbose_name="Moneda"
    )

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

    @property
    def wallet(self):
        """Cuenta principal del negocio (o ``None`` si aún no existe)."""
        return next((w for w in self.wallets.all() if w.role == "primary"), None)

    @property
    def secondary_wallet(self):
        """Cuenta secundaria del negocio (o ``None`` si aún no existe)."""
        return next((w for w in self.wallets.all() if w.role == "secondary"), None)

    @property
    def wallets_by_currency(self) -> dict[str, object]:
        """Mapa moneda -> billetera del negocio (útil para rutear pagos)."""
        return {w.currency: w for w in self.wallets.all()}