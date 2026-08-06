"""views — Endpoints CRUD de ``subscriptions`` (mensualidades).

Rutas:
- ``GET/POST /api/subscriptions``
- ``GET/PATCH/DELETE /api/subscriptions/<id>``
"""

from __future__ import annotations

from rest_framework import status, viewsets
from rest_framework.response import Response

from apps.core.permissions import IsOwner
from apps.subscriptions.models import Subscription
from apps.subscriptions.serializers import SubscriptionSerializer


class SubscriptionViewSet(viewsets.ModelViewSet):
    """CRUD de mensualidades del usuario autenticado."""

    permission_classes = [IsOwner]
    serializer_class = SubscriptionSerializer

    def get_queryset(self):
        """Mensualidades del usuario, con derivados calculados."""
        return Subscription.objects.filter(user=self.request.user)

    def create(self, request, *args, **kwargs):
        """Crea la mensualidad y devuelve su detalle con progreso."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        read = SubscriptionSerializer(instance, context={"request": request})
        return Response(read.data, status=status.HTTP_201_CREATED)