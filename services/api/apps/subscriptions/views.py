"""views — Endpoints CRUD de ``subscriptions`` (mensualidades).

Rutas:
- ``GET/POST /api/subscriptions``
- ``GET/PATCH/DELETE /api/subscriptions/<id>``
- ``POST /api/subscriptions/<id>/renew``
"""

from __future__ import annotations

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.permissions import IsOwner
from apps.subscriptions.models import Subscription
from apps.subscriptions.serializers import (
    SubscriptionRenewSerializer,
    SubscriptionSerializer,
)
from apps.subscriptions.services import renew_subscription


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

    @action(detail=True, methods=["post"], url_path="renew")
    def renew(self, request, pk=None):
        """Renueva la mensualidad creando el gasto registrado.

        Body: ``{"wallet": "<id-cuenta>", "amount": "12.50"}``. La cuenta debe
        pertenecer al usuario; el monto se registra como egreso pagado.
        """
        subscription = self.get_object()
        serializer = SubscriptionRenewSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        renewed = renew_subscription(
            subscription,
            wallet=serializer.validated_data["wallet"],
            amount=serializer.validated_data["amount"],
        )
        read = SubscriptionSerializer(renewed, context={"request": request})
        return Response(read.data, status=status.HTTP_200_OK)