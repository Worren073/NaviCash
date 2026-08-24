"""views — Endpoints de ``notifications``.

- ``GET /api/notifications``: regenera las alertas según el estado actual y
  devuelve las recientes con el conteo de no leídas.
- ``POST /api/notifications/read-all``: marca todas como leídas.
- ``POST /api/notifications/<id>/read``: marca una como leída.
- Web Push: ``GET /api/push/vapid-key``, ``POST/DELETE /api/push/subscriptions``
  y el disparo externo ``POST /api/internal/tick`` (token compartido, lo llama
  el cron horario de GitHub Actions; ver apps/notifications/services.tick).
"""

from __future__ import annotations

import hmac

from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ViewSet

from apps.notifications.models import Notification, PushSubscription
from apps.notifications.serializers import (
    NotificationSerializer,
    PushSubscriptionSerializer,
)
from apps.notifications.services import refresh_notifications, tick


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


# ---------------------------------------------------------------------------
# Web Push: suscripciones y disparo externo
# ---------------------------------------------------------------------------


class VapidPublicKeyView(APIView):
    """Clave pública VAPID para que el navegador cifre su suscripción."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not settings.VAPID_PUBLIC_KEY:
            return Response(
                {"detail": "Web push no está configurado en el servidor."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({"publicKey": settings.VAPID_PUBLIC_KEY})


class PushSubscriptionView(GenericAPIView):
    """Alta/baja de suscripciones push del usuario autenticado.

    POST es idempotente por ``endpoint`` (re-suscripción actualiza claves).
    """

    permission_classes = [IsAuthenticated]
    serializer_class = PushSubscriptionSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        PushSubscription.objects.update_or_create(
            user=request.user,
            endpoint=data["endpoint"],
            defaults={
                "p256dh": data["keys"]["p256dh"],
                "auth": data["keys"]["auth"],
                "user_agent": (data.get("user_agent") or "")[:200],
            },
        )
        return Response(
            {"detail": "Suscripción push registrada."},
            status=status.HTTP_201_CREATED,
        )

    def delete(self, request):
        endpoint = request.query_params.get("endpoint") or (
            request.data or {}
        ).get("endpoint")
        if not endpoint:
            return Response(
                {"detail": "endpoint es obligatorio."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        deleted, _ = PushSubscription.objects.filter(
            user=request.user, endpoint=endpoint
        ).delete()
        if not deleted:
            return Response(
                {"detail": "No existe esa suscripción."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response({"detail": "Suscripción push eliminada."})


class InternalTickView(APIView):
    """POST /api/internal/tick — genera alertas nuevas y envía los pushes.

    Protegido por token compartido (``INTERNAL_TOKEN``) en lugar de JWT: lo
    llama un cron externo (GitHub Actions), no un usuario.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        provided = request.headers.get("X-Internal-Token", "")
        configured = settings.INTERNAL_TOKEN
        # compare_digest evita filtrar el token por tiempo de comparación.
        if not configured or not hmac.compare_digest(provided, configured):
            return Response(
                {"detail": "No autorizado."}, status=status.HTTP_403_FORBIDDEN
            )
        result = tick()
        if result is None:
            return Response(
                {"detail": "Un ciclo anterior sigue en curso."},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(result)