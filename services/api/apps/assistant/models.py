"""models — Mensajes y memoria del asistente Navi.

La conversación se agrupa en sesiones (``session_id``) para poder recuperar el
historial; solo se persisten los turnos de texto, nunca datos de contexto ni
credenciales.

``NaviMemory`` almacena preferencias aprendidas del usuario (asociaciones
concepto↔cuenta, glosarios personales, notas explícitas) para que Navi se
vuelva más certero con el uso.
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
        indexes = [
            # Patrón real: historial de una sesión por usuario (AUDIT A9).
            models.Index(
                fields=["user", "session_id", "created_at"],
                name="chat_user_session_created_idx",
            ),
        ]

    def __str__(self) -> str:
        """Representación: rol + recorte del contenido."""
        return f"{self.role}: {self.content[:60]}"


class NaviMemory(OwnedModel):
    """Preferencia aprendida de un usuario por Navi.

    Clave canónica de la preferencia (ej. ``wallet_para:gasolina``,
    ``personalizado:frase_favorita``) ligada a un valor de texto; cada uso
    refuerza el registro.  ``fuente`` indica si se aprendió automáticamente
    de un registro exitoso o si el usuario la pidió explícitamente.

    Sobrevive al ``purge_assistant`` (que solo limpia ``ChatMessage``).
    """

    FUENTE_AUTO = "auto"
    FUENTE_USUARIO = "usuario"
    FUENTE_CHOICES = [
        (FUENTE_AUTO, "Aprendido automáticamente"),
        (FUENTE_USUARIO, "Guardado por el usuario"),
    ]

    clave = models.CharField(max_length=80, verbose_name="Clave")
    valor = models.CharField(max_length=200, verbose_name="Valor")
    fuente = models.CharField(max_length=8, choices=FUENTE_CHOICES, default=FUENTE_AUTO, verbose_name="Fuente")
    usos = models.PositiveIntegerField(default=1, verbose_name="Usos")
    ultimo_uso = models.DateTimeField(auto_now=True, verbose_name="Último uso")

    class Meta:
        verbose_name = "Memoria del asistente"
        verbose_name_plural = "Memorias del asistente"
        ordering = ["-usos", "-ultimo_uso"]
        constraints = [
            models.UniqueConstraint(fields=["user", "clave"], name="navimemory_user_clave_uniq"),
        ]
        indexes = [
            models.Index(fields=["user", "usos"], name="memi_user_usos_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.clave}={self.valor} ({self.usos} usos)"