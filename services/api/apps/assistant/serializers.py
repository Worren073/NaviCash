"""serializers — Entrada/salida del chat del asistente.

La respuesta es plana (texto + opcional ``actions``) para que el frontend la
renderice sin dependencias del backend; nunca se serializa el contexto.
"""

from rest_framework import serializers

from apps.assistant.models import ChatMessage

#: Tamaño máximo de un clip de voz (10 MB ≈ varios minutos de audio AAC).
#: El límite del proveedor (Whisper) es 25 MB; dejamos margen de sobra.
MAX_AUDIO_BYTES = 10 * 1024 * 1024

#: Content-types aceptados (los que produce MediaRecorder y acepta Whisper).
ALLOWED_AUDIO_TYPES = {
    "audio/mp4",
    "audio/aac",
    "audio/m4a",
    "audio/webm",
    "audio/mpeg",
    "audio/mp3",
    "audio/wav",
    "audio/x-wav",
    "audio/x-m4a",
    "audio/ogg",
}


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


class TranscriptionRequestSerializer(serializers.Serializer):
    """Validación del clip de audio a transcribir.

    Campos:
        audio: archivo de audio (multipart) con el mensaje de voz del usuario.
    """

    audio = serializers.FileField(
        error_messages={
            "required": "Adjunta un audio para transcribir.",
            "empty": "El audio está vacío.",
        },
    )

    def validate_audio(self, value):
        """Rechaza clips demasiado grandes o con formato no soportado."""
        if value.size > MAX_AUDIO_BYTES:
            raise serializers.ValidationError("El audio es demasiado grande (máximo 10 MB).")
        content_type = (getattr(value, "content_type", "") or "").lower()
        if content_type and content_type not in ALLOWED_AUDIO_TYPES:
            raise serializers.ValidationError("Formato de audio no soportado.")
        return value