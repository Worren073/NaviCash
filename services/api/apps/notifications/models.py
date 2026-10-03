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
    ("expense_nudge", "Recordatorio de registro"),
    ("invoice_overdue", "Factura vencida"),
    ("invoice_paid", "Factura pagada"),
    ("product_low_stock", "Stock bajo"),
    ("system", "Sistema"),
]

#: Ámbito de la notificación (separa Personales de Negocio).
SCOPE_CHOICES = [
    ("personal", "Personal"),
    ("business", "Negocio"),
]


class PushSubscription(OwnedModel):
    """Suscripción Web Push (endpoint + claves de cifrado) del usuario.

    Campos:
        endpoint: URL única que asigna el servicio push del navegador
            (FCM/APNs/Mozilla); es la dirección a la que se envía el push.
        p256dh / auth: claves públicas de cifrado ECDH que el navegador
            entregó al suscribirse (necesarias para cifrar el payload).
        user_agent: navegador/dispositivo declarado por el frontend, solo
            informativo para depurar suscripciones duplicadas.
        last_success_at: último envío aceptado; las respuestas 404/410 del
            servicio push provocan la baja automática (ver services.py).
    """

    endpoint = models.URLField(
        max_length=500,
        unique=True,
        verbose_name="Endpoint push",
    )
    p256dh = models.CharField(max_length=120, verbose_name="Clave p256dh")
    auth = models.CharField(max_length=60, verbose_name="Secreto auth")
    user_agent = models.CharField(
        max_length=200, blank=True, default="", verbose_name="Navegador"
    )
    last_success_at = models.DateTimeField(
        null=True, blank=True, verbose_name="Último envío OK"
    )

    class Meta:
        verbose_name = "Suscripción push"
        verbose_name_plural = "Suscripciones push"
        ordering = ["-created_at"]
        indexes = [
            # Tick: iterar rápido las suscripciones de cada usuario.
            models.Index(fields=["user"], name="push_user_idx"),
        ]

    def __str__(self) -> str:
        """Representación corta: dueño + cola del endpoint."""
        return f"{self.user} → …{self.endpoint[-24:]}"


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
    scope = models.CharField(
        max_length=10,
        choices=SCOPE_CHOICES,
        default="personal",
        db_index=True,
        verbose_name="Ámbito",
    )
    title = models.CharField(max_length=160, verbose_name="Título")
    message = models.CharField(max_length=255, verbose_name="Mensaje")
    read = models.BooleanField(default=False, verbose_name="Leída")
    extra = models.JSONField(default=dict, blank=True, verbose_name="Referencias")

    class Meta:
        verbose_name = "Notificación"
        verbose_name_plural = "Notificaciones"
        ordering = ["-created_at"]
        indexes = [
            # Patrón real: últimas notificaciones por usuario y ámbito.
            models.Index(fields=["user", "scope", "-created_at"], name="notif_user_scope_created_idx"),
            # Patrón real: conteo de no leídas del usuario y ámbito.
            models.Index(fields=["user", "scope", "read"], name="notif_user_scope_read_idx"),
        ]
        constraints = [
            # Dedupe atómico de la regeneración write-on-GET (AUDIT A8):
            # una sola alerta por (usuario, ámbito, tipo, referencia).
            models.UniqueConstraint(
                fields=["user", "scope", "kind", "extra"],
                name="uniq_notification_user_scope_kind_extra",
            ),
        ]

    def __str__(self) -> str:
        """Representación: título (leída o no)."""
        return f"{self.title} (leída={self.read})"
