"""Assistant — Rutas del asistente conversacional Navi.

Endpoints:
- ``POST /api/assistant/messages``: envía un turno y devuelve la respuesta.
- ``GET /api/assistant/messages?session_id=<uuid>``: historial de la sesión.
"""

from django.urls import path

from apps.assistant.views import ChatHistoryView, ChatView

urlpatterns = [
    path("assistant/messages", ChatView.as_view(), name="assistant-chat"),
    path("assistant/messages/history", ChatHistoryView.as_view(), name="assistant-history"),
]