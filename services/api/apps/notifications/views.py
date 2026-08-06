"""views — Endpoints de ``notifications``.

- ``GET /api/notifications``: regenera las alertas según el estado actual y
  devuelve las recientes con el conteo de no leídas.
- ``POST /api/notifications/read-all``: marca todas como leídas.
- ``POST /api/notifications/<id>/read``: marca una como leída.
"""

from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from apps.notifications.models import Notification
from apps.notifications.serializers import NotificationSerializer
from apps.notifications.services import refresh_notifications


class NotificationViewSet(ViewSet):
    """Alertas del usuario autenticado."""

    permission_classes = [IsAuthenticated]

    def list(self, request):
        """GET: regenera y devuelve notificaciones + contador de no leídas."""
        items = refresh_notifications(request.user)
        data = NotificationSerializer(items, many=True).data
        unread = Notification.objects.filter(user=request.user, read=False).count()
        return Response({"results": data, "unread_count": unread})

    @action(detail=False, methods=["post"], url_path="read-all")
    def read_all(self, request):
        """Marca todas las notificaciones del usuario como leídas."""
        Notification.objects.filter(user=request.user, read=False).update(read=True)
        return Response({"detail": "Notificaciones marcadas como leídas."})

    @action(detail=True, methods=["post"], url_path="read")
    def mark_read(self, request, pk=None):
        """Marca como leída una notificación concreta."""
        notif = get_object_or_404(Notification, user=request.user, pk=pk)
        if not notif.read:
            notif.read = True
            notif.save(update_fields=["read"])
        return Response(
            NotificationSerializer(notif).data, status=status.HTTP_200_OK
        )