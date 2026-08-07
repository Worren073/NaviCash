"""models — Mensajes de la conversación con el asistente.

La conversación se agrupa en sesiones (``session_id``) para poder recuperar el
historial; solo se persisten los turnos de texto, nunca datos de contexto ni
credenciales.
"""

from __future__ import annotations

import uuid

from django.db import models

from apps.core.models import OwnedModel


class ChatMessage(OwnedModel):
    """Mensaje de la conversación del usuario con Navi.

    Campos:
        session_id: identificador de sesión agrupador (uuid del cliente).
        role: "user" (pregunta) o "assistant" (respuesta).
        text: contenido del turno.
    """

    session_id = models.UUIDField(
        default=uuid.uuid4, editable=False, db_index=True, verbose_name="Sesión"
    )
    role = models.CharField(max_length=12, choices=[("user", "Usuario"), ("assistant", "Asistente")], verbose_name="Rol")
    content = models.TextField(verbose_name="Contenido")

    class Meta:
        verbose_name = "Mensaje del chat"
        verbose_name_plural = "Mensajes del chat"
        ordering = ["created_at"]

    def __str__(self) -> str:
        """Representación: rol + recorte del contenido."""
        return f"{self.role}: {self.content[:60]}"