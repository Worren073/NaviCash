"""models — Modelo ``ExchangeRate``: caché e histórico de tasas.

Almacena las cotizaciones del USD (compra/venta/promedio) según la fuente.
La app sólo usa la fuente ``oficial`` (BCV) para conversiones (ADR-03), pero la
tabla guarda histórico por si se requieren auditorías o cambios de fuente.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import models

#: Fuentes de cotización disponibles (oficial = BCV, usada siempre; el resto
#: se guarda por completitud si el proveedor las ofreciera).
RATE_SOURCES = [
    ("oficial", "Oficial (BCV)"),
    ("paralelo", "Paralelo"),
    ("manual", "Manual"),
]


class ExchangeRate(models.Model):
    """Una cotización de USD frente a la moneda local (ej. VES).

    Campos:
        source: origen de la cotización (oficial/paralelo/manual).
        currency: moneda cotizada (ej. VES); frente a 1 USD.
        compra / venta: valores de compra y venta (pueden ser nulos).
        promedio: valor de referencia usado en las conversiones.
        rate_date: fecha de la cotización publicada por la fuente.
        is_stale: True cuando se sirve desde caché sin confirmación reciente.
        input_at: instante en que se guardó en nuestra BD.
    """

    source = models.CharField(max_length=12, choices=RATE_SOURCES, verbose_name="Fuente")
    currency = models.CharField(max_length=3, default="VES", verbose_name="Moneda cotizada")
    compra = models.DecimalField(
        max_digits=20, decimal_places=4, null=True, blank=True, verbose_name="Compra"
    )
    venta = models.DecimalField(
        max_digits=20, decimal_places=4, null=True, blank=True, verbose_name="Venta"
    )
    promedio = models.DecimalField(
        max_digits=20, decimal_places=4, null=True, blank=True, verbose_name="Promedio"
    )
    rate_date = models.DateTimeField(verbose_name="Fecha de la cotización")
    is_stale = models.BooleanField(
        default=False,
        verbose_name="Desactualizada",
        help_text="True si provino de una caché sin confirmación reciente.",
    )
    input_at = models.DateTimeField(auto_now_add=True, verbose_name="Guardada el")

    class Meta:
        verbose_name = "Tasa de cambio"
        verbose_name_plural = "Tasas de cambio"
        ordering = ["-input_at"]
        indexes = [models.Index(fields=["source", "input_at"])]

    def __str__(self) -> str:
        """Representación: fuente, moneda y promedio."""
        return f"{self.get_source_display()} {self.currency} {self.promedio}"

    @property
    def effective_rate(self) -> "Decimal | None":
        """Devuelve el valor a usar para conversiones: promedio si existe.

        Si no hay promedio, usa venta; si no, compra; si ninguno, None.

        Returns:
            Decimal con la tasa efectiva o None si no hay datos.
        """
        for candidate in (self.promedio, self.venta, self.compra):
            if candidate is not None:
                return candidate
        return None