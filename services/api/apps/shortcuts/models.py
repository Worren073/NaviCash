"""models — Modelo ``Shortcut``: atajo de acción rápida.

Los atajos son registros ligeros: el tipo de acción (``kind``) y una
configuración JSON validada mínimamente. Acciones soportadas en el MVP:

- ``transaction``: abre el form de cobro/pago pre-rellenado
  (config: tipo, moneda, concepto, contact_id, category_id, wallet_id, monto).
- ``goal_contribution``: abre el form de aporte a una meta
  (config: goal_id).
"""

from __future__ import annotations

from django.db import models

from apps.core.models import OwnedModel

#: Tipos de atajo soportados en el MVP.
SHORTCUT_KINDS = [
    ("transaction", "Nueva operación"),
    ("goal_contribution", "Aportar a meta"),
]


class Shortcut(OwnedModel):
    """Un atajo visible en la home del usuario.

    Campos:
        label: etiqueta del botón (ej. "Cobrar a María").
        kind: tipo de acción que dispara.
        config: JSON con los valores pre-rellenados.
        order: posición de ordenación (menor = primero).
        icon: nombre del icono (UI).
    """

    label = models.CharField(max_length=60, verbose_name="Etiqueta")
    kind = models.CharField(max_length=30, choices=SHORTCUT_KINDS, verbose_name="Tipo")
    config = models.JSONField(default=dict, blank=True, verbose_name="Configuración")
    order = models.PositiveSmallIntegerField(default=0, verbose_name="Orden")
    icon = models.CharField(max_length=40, blank=True, default="zap", verbose_name="Icono")

    class Meta:
        verbose_name = "Atajo"
        verbose_name_plural = "Atajos"
        ordering = ["order", "created_at"]

    def __str__(self) -> str:
        """Representación: etiqueta del atajo."""
        return self.label