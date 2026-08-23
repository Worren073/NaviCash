"""views — Endpoints del asistente Navi.

- ``POST /api/assistant/messages``: envía un mensaje al asistente y recibe la
  respuesta. Autenticado y con rate limit dedicado (scope ``assistant``).
- ``GET /api/assistant/messages``: historial persistido de la sesión (opcional
  en esta fase; devuelve los últimos mensajes).

Ambos verifican que la sesión pertenezca al ``request.user``.
"""

import uuid

from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from apps.assistant.models import ChatMessage
from apps.assistant.serializers import (
    ChatMessageSerializer,
    ChatRequestSerializer,
    ChatResponseSerializer,
    TranscriptionRequestSerializer,
)
from apps.assistant.services import chat, transcribe

#: Límite duro del historial (M4): se devuelven como máximo estos mensajes.
HISTORY_LIMIT = 50


class UserScopedRateThrottle(ScopedRateThrottle):
    """Rate limit por usuario autenticado (no por IP) para el scope.

    El chat es personal y hay usuarios detrás de redes compartidas (NAT):
    la cuota (30 msgs/hora) debe contarse por cuenta, no por dirección.
    Los anónimos (sin token) siguen limitándose por IP.
    """

    def get_ident(self, request) -> str:
        if request.user and request.user.is_authenticated:
            return f"user:{request.user.pk}"
        return super().get_ident(request)


class ChatView(GenericAPIView):
    """POST /api/assistant/messages → respuesta de Navi anclada al contexto."""

    serializer_class = ChatRequestSerializer
    permission_classes = [IsAuthenticated]
    throttle_classes = [UserScopedRateThrottle]
    throttle_scope = "assistant"

    def post(self, request) -> Response:
        """Procesa el mensaje del usuario autenticado y devuelve la respuesta."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        result = chat(
            user=request.user,
            message=data["message"],
            session_id=data.get("session_id"),
        )
        return Response(ChatResponseSerializer(result).data, status=status.HTTP_200_OK)


class ChatHistoryView(GenericAPIView):
    """GET /api/assistant/messages?session_id=<uuid> → historial de la sesión."""

    serializer_class = ChatMessageSerializer
    permission_classes = [IsAuthenticated]

    def get(self, request) -> Response:
        """Devuelve los últimos ``HISTORY_LIMIT`` mensajes en orden cronológico.

        M4: el historial se lee con límite duro (50); se ordena DESC para
        tomar los más recientes y se invierte para que el cliente los reciba
        cronológicos. La paginación formal se hará en una iteración posterior.
        """
        session_id = request.query_params.get("session_id")
        if not session_id:
            return Response(
                {"detail": "session_id es obligatorio para ver el historial."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            uuid.UUID(session_id)
        except ValueError:
            return Response(
                {"detail": "session_id debe ser un UUID válido."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        rows = list(
            ChatMessage.objects.filter(user=request.user, session_id=session_id)
            .order_by("-created_at")[:HISTORY_LIMIT]
        )
        rows.reverse()
        serializer = self.get_serializer(rows, many=True)
        return Response(serializer.data)


class TranscriptionView(GenericAPIView):
    """POST /api/assistant/transcribe → transcript del clip de voz del usuario.

    Recibe un multipart con el audio grabado por el cliente (MediaRecorder),
    lo transcribe con el proveedor configurado (Whisper o mock) y devuelve
    ``{"transcript": str}`` listo para enviar al chat.
    """

    serializer_class = TranscriptionRequestSerializer
    permission_classes = [IsAuthenticated]
    throttle_classes = [UserScopedRateThrottle]
    throttle_scope = "transcribe"

    def post(self, request) -> Response:
        """Transcribe el clip y devuelve el texto para el chat de voz."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        upload = serializer.validated_data["audio"]
        result = transcribe(upload.read(), upload.name or "audio")
        return Response({"transcript": result["transcript"]}, status=status.HTTP_200_OK)