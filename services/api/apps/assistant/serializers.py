"""serializers — Entrada/salida del chat del asistente.

La respuesta es plana (texto + opcional ``actions``) para que el frontend la
renderice sin dependencias del backend; nunca se serializa el contexto.
"""

from rest_framework import serializers

from apps.assistant.models import ChatMessage


class ChatRequestSerializer(serializers.Serializer):
    """Validación de la petición al chat del asistente.

    Campos:
        message: texto del usuario (obligatorio, recortado, con longitud máx).
        session_id: identificador de sesión (uuid opcional; por defecto el
            backend asigna uno nuevo).
    """

    message = serializers.CharField(
        max_length=1000,
        min_length=1,
        trim_whitespace=True,
        error_messages={
            "blank": "Escribe un mensaje para Navi.",
            "max_length": "El mensaje es demasiado largo (más de 1000 caracteres).",
            "min_length": "El mensaje no puede estar vacío.",
        },
    )
    session_id = serializers.UUIDField(required=False)

    def validate_message(self, value: str) -> str:
        """Normaliza el mensaje: colapsa espacios y quita saltos duplicados."""
        return " ".join(value.split())


class ChatResponseSerializer(serializers.Serializer):
    """Salida del asistente: texto y sesión que agrupa la conversación."""

    text = serializers.CharField(read_only=True)
    session_id = serializers.UUIDField(read_only=True)


class ChatMessageSerializer(serializers.ModelSerializer):
    """Respuesta para listar el historial persistido de mensajes."""

    class Meta:
        model = ChatMessage
        fields = ["id", "session_id", "role", "content", "created_at"]