"""models — Modelos de ahorro: SavingsGoal y GoalContribution.

Reglas:
- Una meta tiene un monto objetivo en una moneda (la suma de aportes se calcula
  en la moneda de la meta; si el aporte llega en otra moneda se convierte con
  la tasa del momento y se congela — ver ``GoalContribution.amount_goal_currency``).
- La billetera de origen es opcional: si se indica, el aporte NO toca el saldo
  automáticamente en el MVP (el ahorro se concilia con el ajuste manual).
- Una meta puede afiliarse a una o varias cuentas de ahorro
  (``linked_accounts``, solo billeteras ``tipo="saving"``). Cuando hay cuentas
  afiliadas, el avance de la meta suma el saldo de todas ellas; si no hay,
  el avance proviene solo de los aportes manuales.
"""

from __future__ import annotations

from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models

from apps.core.currency import (
    CURRENCY_CHOICES,
    MONEY_DECIMALS,
    convert_to_usd,
    round_money,
    usd_to_currency,
)
from apps.core.models import OwnedModel
from apps.rates.service import get_current_official_rate


class SavingsGoal(OwnedModel):
    """Meta de ahorro del usuario (ej. "Vacaciones 2027", "Fondo de emergencia").

    Campos:
        name: nombre de la meta.
        target_amount: monto objetivo (en ``currency``).
        currency: moneda del objetivo.
        target_date: fecha límite opcional.
        linked_accounts: cuentas de ahorro (tipo "saving") afiliadas a la meta.
    """

    name = models.CharField(max_length=120, verbose_name="Nombre")
    target_amount = models.DecimalField(
        max_digits=20,
        decimal_places=MONEY_DECIMALS,
        validators=[MinValueValidator(Decimal("0.01"))],
        verbose_name="Monto objetivo",
    )
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default="USD", verbose_name="Moneda")
    target_date = models.DateField(null=True, blank=True, verbose_name="Fecha objetivo")
    linked_accounts = models.ManyToManyField(
        "wallets.Wallet",
        blank=True,
        related_name="linked_goals",
        verbose_name="Cuentas de ahorro afiliadas",
    )

    class Meta:
        verbose_name = "Meta de ahorro"
        verbose_name_plural = "Metas de ahorro"
        ordering = ["created_at"]

    def __str__(self) -> str:
        """Representación: nombre (objetivo)."""
        return f"{self.name} ({self.target_amount} {self.currency})"

    @property
    def linked_accounts_balance(self) -> Decimal:
        """Suma de los saldos de las cuentas afiliadas en la moneda de la meta.

        Las cuentas en la misma moneda se suman directo; las de otra moneda
        convertible (USD↔VES) se convierten con la tasa oficial del día. Las
        cuentas cuya moneda no es convertible se omiten de la suma.
        """
        rate = get_current_official_rate()
        rate_value: "Decimal | None" = rate.effective_rate if rate else None
        total = Decimal("0")
        for account in self.linked_accounts.all():
            if account.currency == self.currency:
                total += account.saldo
            elif self.currency == "USD" and account.currency == "VES" and rate_value:
                total += convert_to_usd(account.saldo, "VES", rate_value)
            elif self.currency == "VES" and account.currency == "USD" and rate_value:
                total += usd_to_currency(account.saldo, "VES", rate_value)
        return total

    @property
    def total_contributed(self) -> Decimal:
        """Avance de la meta: aportes manuales + saldo de cuentas afiliadas.

        Cuando la meta tiene cuentas afiliadas el avance refleja el saldo
        real ahorrado; de lo contrario solo los aportes manuales registrados.
        """
        contributions = self.contributions.aggregate(total=models.Sum("amount_goal_currency"))[
            "total"
        ] or Decimal("0")
        return round_money(Decimal(contributions) + self.linked_accounts_balance)

    @property
    def progress_percent(self) -> Decimal:
        """Porcentaje de avance 0-100 (redondeado a 1 decimal).

        Returns:
            Decimal: ej. 42.5 (avance del 42.5%).
        """
        if self.target_amount <= 0:
            return Decimal("0")
        return round_money((self.total_contributed / self.target_amount) * Decimal("100"))


class GoalContribution(OwnedModel):
    """Aporte individual a una meta de ahorro.

    Campos:
        goal: meta a la que aporta.
        amount: cantidad aportada en ``currency``.
        currency: moneda del aporte.
        amount_goal_currency: equivalente congelado en la moneda de la meta.
        wallet: billetera de origen (opcional; sin efecto de saldo en MVP).
        note: nota opcional.
    """

    goal = models.ForeignKey(
        SavingsGoal,
        on_delete=models.CASCADE,
        related_name="contributions",
        verbose_name="Meta",
    )
    amount = models.DecimalField(max_digits=20, decimal_places=MONEY_DECIMALS, verbose_name="Aporte")
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, verbose_name="Moneda")
    amount_goal_currency = models.DecimalField(
        max_digits=20,
        decimal_places=MONEY_DECIMALS,
        default=Decimal("0"),
        verbose_name="Aporte en la moneda de la meta",
    )
    wallet = models.ForeignKey(
        "wallets.Wallet",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contributions",
        verbose_name="Billetera de origen",
    )
    note = models.CharField(max_length=200, blank=True, verbose_name="Nota")

    class Meta:
        verbose_name = "Aporte"
        verbose_name_plural = "Aportes"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        """Representación: cantidad a la meta."""
        return f"{self.amount} {self.currency} → {self.goal.name}"