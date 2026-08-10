"""models — Modelo ``Notification``: alertas generadas para el usuario.

Las notificaciones se generan bajo demanda (``services.refresh_notifications``)
según el estado actual del dominio: operaciones con vencimiento próximo o ya
vencidas, y metas de ahorro alcanzadas. El modelo persiste cada alerta para
soportar el estado "leída" del usuario.
"""

from __future__ import annotations

from django.db import models

from apps.core.models import OwnedModel

#: Tipos de notificación del MVP.
NOTIFICATION_KINDS = [
    ("due_soon", "Vence pronto"),
    ("overdue", "Vencida"),
    ("goal_reached", "Meta alcanzada"),
    ("system", "Sistema"),
]


class Notification(OwnedModel):
    """Una alerta individual del usuario.

    Campos:
        kind: categoría de la alerta (vencimiento, retraso, meta, sistema).
        title: encabezado corto.
        message: detalle legible.
        read: si el usuario ya la vio/marcó como leída.
        extra: JSON con referencias (transaction_id, goal_id) para deduplicar.
    """

    kind = models.CharField(max_length=20, choices=NOTIFICATION_KINDS, verbose_name="Tipo")
    title = models.CharField(max_length=160, verbose_name="Título")
    message = models.CharField(max_length=255, verbose_name="Mensaje")
    read = models.BooleanField(default=False, verbose_name="Leída")
    extra = models.JSONField(default=dict, blank=True, verbose_name="Referencias")

    class Meta:
        verbose_name = "Notificación"
        verbose_name_plural = "Notificaciones"
        ordering = ["-created_at"]
        indexes = [
            # Patrón real: últimas notificaciones por usuario (AUDIT A9).
            models.Index(fields=["user", "-created_at"], name="notif_user_created_idx"),
            # Patrón real: conteo de no leídas del usuario (AUDIT A9).
            models.Index(fields=["user", "read"], name="notif_user_read_idx"),
        ]
        constraints = [
            # Dedupe atómico de la regeneración write-on-GET (AUDIT A8):
            # una sola alerta por (usuario, tipo, referencia).
            models.UniqueConstraint(
                fields=["user", "kind", "extra"],
                name="uniq_notification_user_kind_extra",
            ),
        ]

    def __str__(self) -> str:
        """Representación: título (leída o no)."""
        return f"{self.title} (leída={self.read})"
