"""serializers — Entrada/salida del chat del asistente.

La respuesta es plana (texto + opcional ``actions``) para que el frontend la
renderice sin dependencias del backend; nunca se serializa el contexto.
"""

from rest_framework import serializers

from apps.assistant.models import ChatMessage

#: Tamaño máximo de un clip de voz (10 MB ≈ varios minutos de audio AAC).
#: El límite del proveedor (Whisper) es 25 MB; dejamos margen de sobra.
MAX_AUDIO_BYTES = 10 * 1024 * 1024

#: Extensiones aceptadas (las que produce MediaRecorder y acepta Whisper).
#: El content-type del multipart no es fiable (iOS Safari lo manda a veces como
#: ``application/octet-stream`` o vacío), así que se valida por extensión.
ALLOWED_AUDIO_EXTENSIONS = {
    ".mp4",
    ".m4a",
    ".aac",
    ".webm",
    ".mp3",
    ".mpeg",
    ".wav",
    ".ogg",
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
        """Rechaza clips demasiado grandes o con extensión no soportada.

        El content-type que manda el navegador es poco fiable (Safari puede
        enviar ``application/octet-stream`` aunque el audio sea mp4), así que se
        valida por extensión del nombre; el proveedor real (Whisper) es quien
        juzga el contenido.
        """
        if value.size > MAX_AUDIO_BYTES:
            raise serializers.ValidationError("El audio es demasiado grande (máximo 10 MB).")
        name = (getattr(value, "name", "") or "").lower()
        extension = f".{name.rsplit('.', 1)[-1]}" if "." in name else ""
        if extension not in ALLOWED_AUDIO_EXTENSIONS:
            raise serializers.ValidationError("Formato de audio no soportado.")
        return value


class NaviMemorySerializer(serializers.ModelSerializer):
    """Serialización de una preferencia aprendida por Navi."""

    class Meta:
        from apps.assistant.models import NaviMemory as _NaviMemory
        model = _NaviMemory
        fields = ["id", "clave", "valor", "fuente", "usos", "ultimo_uso"]
        read_only_fields = fields


class NaviMemoryCreateSerializer(serializers.Serializer):
    """Entrada para crear una memoria manualmente desde el Perfil."""

    texto = serializers.CharField(max_length=200, min_length=5, trim_whitespace=True)

    def validate_texto(self, value: str) -> str:
        if len(value) < 5:
            raise serializers.ValidationError("La nota es muy corta.")
        return value