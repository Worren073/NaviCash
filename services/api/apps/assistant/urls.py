"""Assistant — Rutas del asistente conversacional Navi.

Endpoints:
- ``POST /api/assistant/messages``: envía un turno y devuelve la respuesta.
- ``GET /api/assistant/messages?session_id=<uuid>``: historial de la sesión.
- ``POST /api/assistant/transcribe``: transcribe un clip de voz (chat por voz).
- ``GET  /api/assistant/memory``: preferencias aprendidas.
- ``POST /api/assistant/memory``: guardar nota manual.
- ``DELETE /api/assistant/memory?all=1``: borrar todas.
- ``DELETE /api/assistant/memory/<id>``: borrar una individual.
"""

from django.urls import path

from apps.assistant.views import (
    ChatHistoryView,
    ChatView,
    NaviMemoryDetailView,
    NaviMemoryListView,
    TranscriptionView,
)

urlpatterns = [
    path("assistant/messages", ChatView.as_view(), name="assistant-chat"),
    path("assistant/messages/history", ChatHistoryView.as_view(), name="assistant-history"),
    path("assistant/transcribe", TranscriptionView.as_view(), name="assistant-transcribe"),
    path("assistant/memory", NaviMemoryListView.as_view(), name="assistant-memory"),
    path("assistant/memory/<uuid:pk>", NaviMemoryDetailView.as_view(), name="assistant-memory-detail"),
]