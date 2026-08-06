"""models — Modelo ``Subscription``: mensualidad con avance por tiempo.

Una mensualidad es un compromiso periódico acotado entre dos fechas (inicio y
cierre). El progreso se mide por el tiempo transcurrido del período:
- antes del inicio: 0%
- durante: (días transcurridos / días totales) * 100
- tras el cierre: 100%
"""

from __future__ import annotations

from decimal import Decimal

from django.db import models
from django.utils import timezone

from apps.core.models import OwnedModel

#: Estados derivados de la fecha actual.
SUBSCRIPTION_STATUS = [
    ("proxima", "Próxima"),
    ("activa", "Activa"),
    ("finalizada", "Finalizada"),
]

#: Colores sugeridos para la mensualidad (armonizan con el glass).
SUBSCRIPTION_COLORS = [
    "#10b981",  # esmeralda
    "#006a61",  # teal (primario)
    "#2563eb",  # azul
    "#7c3aed",  # violeta
    "#0891b2",  # cian
    "#16a34a",  # verde
    "#d97706",  # ámbar
    "#ea580c",  # naranja
    "#e11d48",  # rosa
    "#475569",  # slate
]


class Subscription(OwnedModel):
    """Compromiso periódico del usuario con período acotado.

    Campos:
        name: nombre visible (ej. "Gimnasio", "Netflix").
        color: color identificador (hex) usado por el icono y la barra de progreso.
        start_date: fecha de inicio del período.
        end_date: fecha de cierre (>= start_date).
    """

    name = models.CharField(max_length=120, verbose_name="Nombre")
    color = models.CharField(
        max_length=9,
        default="#10b981",
        blank=True,
        verbose_name="Color",
        help_text="Color identificador (hex) del icono y la barra de progreso.",
    )
    start_date = models.DateField(verbose_name="Inicia el")
    end_date = models.DateField(verbose_name="Finaliza el")

    class Meta:
        verbose_name = "Mensualidad"
        verbose_name_plural = "Mensualidades"
        ordering = ["start_date"]

    def __str__(self) -> str:
        """Representación: nombre (período)."""
        return f"{self.name} ({self.start_date} → {self.end_date})"

    @classmethod
    def _progress_between(cls, today, start, end) -> Decimal:
        """Progreso por tiempo entre dos fechas (inyectable en tests).

        Args:
            today: fecha de referencia.
            start: fecha de inicio del período.
            end: fecha de cierre del período.

        Returns:
            Decimal entre 0.0 y 100.0 con 1 decimal.
        """
        if end < today:
            return Decimal("100.0")
        if today < start:
            return Decimal("0.0")
        total = max(1, (end - start).days)
        elapsed = max(0, (today - start).days)
        return Decimal(str(round(min(100, elapsed / total * 100), 1)))

    @property
    def progress_percent(self) -> Decimal:
        """Porcentaje del período transcurrido (0.0–100.0)."""
        return self._progress_between(timezone.localdate(), self.start_date, self.end_date)

    @property
    def days_total(self) -> int:
        """Días totales del período (>= 0)."""
        return max(0, (self.end_date - self.start_date).days)

    @property
    def days_elapsed(self) -> int:
        """Días transcurridos del período (acotado a [0, days_total])."""
        today = timezone.localdate()
        if today <= self.start_date:
            return 0
        return min(self.days_total, (today - self.start_date).days)

    @property
    def status(self) -> str:
        """Estado derivado: próxima / activa / finalizada."""
        today = timezone.localdate()
        if today < self.start_date:
            return "proxima"
        if today > self.end_date:
            return "finalizada"
        return "activa"