"""views — Endpoints del asistente Navi.

- ``POST /api/assistant/messages``: envía un mensaje al asistente y recibe la
  respuesta. Autenticado y con rate limit dedicado (scope ``assistant``).
- ``GET /api/assistant/messages``: historial persistido de la sesión (opcional
  en esta fase; devuelve los últimos mensajes).

Ambos verifican que la sesión pertenezca al ``request.user``.
"""

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
)
from apps.assistant.services import chat


class ChatView(GenericAPIView):
    """POST /api/assistant/messages → respuesta de Navi anclada al contexto."""

    serializer_class = ChatRequestSerializer
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
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
        """Devuelve los mensajes persistidos de la sesión indicada (del usuario)."""
        session_id = request.query_params.get("session_id")
        if not session_id:
            return Response(
                {"detail": "session_id es obligatorio para ver el historial."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        rows = ChatMessage.objects.filter(user=request.user, session_id=session_id)
        serializer = self.get_serializer(rows, many=True)
        return Response(serializer.data)