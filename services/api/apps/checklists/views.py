"""views — Endpoints CRUD de ``checklists`` (listas de compras).

Rutas:
- ``GET/POST /api/checklists``
- ``GET/PATCH/DELETE /api/checklists/<id>``
- ``POST /api/checklists/<id>/complete``
"""

from __future__ import annotations

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.checklists.models import ShoppingList
from apps.checklists.serializers import (
    ChecklistCompleteSerializer,
    ShoppingListSerializer,
)
from apps.checklists.services import complete_shopping_list
from apps.core.permissions import IsOwner


class ShoppingListViewSet(viewsets.ModelViewSet):
    """CRUD de listas de compras del usuario autenticado."""

    permission_classes = [IsOwner]
    serializer_class = ShoppingListSerializer

    def get_queryset(self):
        """Listas del usuario con sus productos precargados."""
        return ShoppingList.objects.filter(user=self.request.user).prefetch_related("items")

    def create(self, request, *args, **kwargs):
        """Crea la lista con sus productos y devuelve el detalle con derivados."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        read = self.get_serializer(instance, context={"request": request})
        return Response(read.data, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        """Soft-delete (C4): oculta la lista sin tocar su historial de pago."""
        instance = self.get_object()
        instance.soft_delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="complete")
    def complete(self, request, pk=None):
        """Completa la lista creando el egreso y descontando la cuenta elegida.

        Body: ``{"wallet": "<id-cuenta>", "total_real": "123.45"}``. La cuenta
        debe pertenecer al usuario y usar la moneda de la lista; el gasto se
        registra como pago pagado (descuenta el saldo).
        """
        shopping_list = self.get_object()
        serializer = ChecklistCompleteSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        completed = complete_shopping_list(
            shopping_list,
            wallet=serializer.validated_data["wallet"],
            total_real=serializer.validated_data["total_real"],
        )
        read = self.get_serializer(completed, context={"request": request})
        return Response(read.data, status=status.HTTP_200_OK)