"""models — Modelos base transversales de NaviCash.

Proveen primitivas comunes (identificador UUID en lugar de int secuencial,
marcas temporales automáticas y confirmación genérica de propiedad del usuario),
que las apps de dominio reutilizan.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


class UUIDModel(models.Model):
    """Modelo abstracto cuya PK es un UUID (v4, no secuencial).

    Ventajas: no expone el volumen de datos (aunque la API igual puede ser
    pública en home), imposible de adivinar/enumerar para otras cuentas, y
    único para todas las tablas a futuro.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class TimeStampedModel(UUIDModel):
    """Modelo abstracto con ``created_at`` y ``updated_at`` automáticos."""

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Creado el")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Actualizado el")

    class Meta:
        abstract = True
        ordering = ["-created_at"]


class OwnedModel(TimeStampedModel):
    """Modelo abstracto que liga sus registros a un usuario.

    Todos los dominios del MVP (billeteras, operaciones, metas, atajos...)
    pertenecen a un único usuario; heredar de aquí asegura el scoping y
    simplifica los permisos.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s",
        verbose_name="Usuario",
    )

    class Meta:
        abstract = True