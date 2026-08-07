"""views — Endpoints de metas y aportes.

- CRUD en ``/api/savings``.
- ``POST /api/savings/<id>/contributions``: registrar aporte.
- ``GET /api/savings/<id>/contributions``: listar aportes de la meta.
"""

from __future__ import annotations

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.permissions import IsOwner
from apps.savings.models import GoalContribution, SavingsGoal
from apps.savings.serializers import (
    ContributionSerializer,
    GoalReadSerializer,
    GoalWriteSerializer,
)


class GoalViewSet(viewsets.ModelViewSet):
    """CRUD de metas de ahorro con acciones de aportes."""

    permission_classes = [IsOwner]

    def get_queryset(self):
        """Metas del usuario autenticado, con aportes precargados."""
        return SavingsGoal.objects.filter(user=self.request.user).prefetch_related("contributions")

    def get_serializer_class(self):
        """Escritura vs lectura según la acción."""
        if self.action in ("create", "update", "partial_update"):
            return GoalWriteSerializer
        return GoalReadSerializer

    def create(self, request, *args, **kwargs):
        """Crea la meta y devuelve su detalle con progreso."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        read = GoalReadSerializer(instance, context={"request": request})
        return Response(read.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        """Actualiza la meta y devuelve su detalle con progreso."""
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        read = GoalReadSerializer(instance, context={"request": request})
        return Response(read.data)

    @action(detail=True, methods=["get", "post"])
    def contributions(self, request, pk=None):
        """GET: lista aportes. POST: registra un aporte a la meta."""
        goal = self.get_object()
        if request.method == "GET":
            rows = goal.contributions.select_related("wallet").order_by("-created_at")
            data = [
                {
                    "id": c.pk,
                    "amount": str(c.amount),
                    "currency": c.currency,
                    "amount_goal_currency": str(c.amount_goal_currency),
                    "wallet": c.wallet_id,
                    "wallet_name": c.wallet.name if c.wallet else None,
                    "note": c.note,
                    "created_at": c.created_at,
                }
                for c in rows
            ]
            return Response(data)

        serializer = ContributionSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        contribution = serializer.create_contribution(goal, request.user)
        return Response(
            {"detail": "Aporte registrado.", "contribution_id": contribution.pk},
            status=status.HTTP_201_CREATED,
        )