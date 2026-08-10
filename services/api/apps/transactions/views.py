"""views — Endpoints de operaciones, categorías y contactos.

``TransactionViewSet``:
- CRUD de operaciones del usuario.
- ``POST /api/transactions/<id>/state``: cambia el estado (pagado/cancelado/
  pendiente) usando ``set_state`` (ver services).
- Al eliminar una operación pagada se revierte la billetera automáticamente.
"""

from __future__ import annotations

from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.exceptions import BusinessRuleError
from apps.core.permissions import IsOwner
from apps.transactions.models import Category, Contact, Transaction
from apps.transactions.serializers import (
    CategorySerializer,
    ContactSerializer,
    TransactionActionSerializer,
    TransactionReadSerializer,
    TransactionWriteSerializer,
)
from apps.transactions.services import _apply_to_wallet


class TransactionViewSet(viewsets.ModelViewSet):
    """CRUD y transiciones de estado de las operaciones del usuario."""

    permission_classes = [IsOwner]

    def get_queryset(self):
        """Operaciones del usuario autenticado con filtros activos.

        Filtros por query param: ``estado`` (incluye el derivado "retrasado"),
        ``tipo``, ``moneda``, ``wallet``.
        """
        qs = (
            Transaction.objects.filter(user=self.request.user)
            .select_related("wallet", "category", "contact", "dest_wallet")
            .order_by("-fecha", "-created_at")
        )

        # Filtros "materializados" (campo directo).
        for field in ("tipo", "moneda", "wallet"):
            value = self.request.query_params.get(field)
            if value:
                qs = qs.filter(**{field: value})

        fecha = self.request.query_params.get("fecha")
        if fecha:
            qs = qs.filter(fecha=fecha)

        estado = self.request.query_params.get("estado")
        if estado == "retrasado":
            # "retrasado" es un estado derivado: se filtra en Python, no en SQL.
            qs = [t for t in qs if t.is_overdue]
            return qs
        if estado:
            qs = qs.filter(estado=estado)
        return qs

    def get_serializer_class(self):
        """Usa el serializador de escritura para mutaciones y de lectura para GET."""
        if self.action in ("create", "update", "partial_update"):
            return TransactionWriteSerializer
        return TransactionReadSerializer

    def _guard_transfer_readonly(self, instance: Transaction) -> None:
        """Bloquea edición/borrado/transición de una transferencia.

        Las transferencias son inmutables por diseño: para revertirlas el
        usuario hace una transferencia en sentido contrario.
        """
        if instance.tipo == "transferencia":
            raise BusinessRuleError(
                "Una transferencia no puede editarse ni eliminarse; "
                "para revertirla haz una transferencia en sentido contrario."
            )

    def perform_update(self, serializer):
        """Evita editar transferencias (inmutables)."""
        self._guard_transfer_readonly(serializer.instance)
        super().perform_update(serializer)

    def perform_destroy(self, instance: Transaction) -> None:
        """Soft-delete de la operación revirtiendo la billetera si estaba pagada.

        C4: el historial financiero nunca se borra físicamente: la operación
        se marca ``is_deleted`` y desaparece de la API (manager ``objects``).
        Se ejecuta en una transacción atómica para no dejar el saldo a medias
        (R9). Si revertir fallara (saldo insuficiente), la eliminación aborta.
        """
        self._guard_transfer_readonly(instance)
        with transaction.atomic():
            if instance.estado == "pagado":
                _apply_to_wallet(instance, reverse=True)
            instance.soft_delete()

    @action(detail=True, methods=["post"])
    def state(self, request, pk=None):
        """Cambia el estado de la operación.

        Body ``{"estado": "pagado|cancelado|pendiente"}``. Devuelve la
        operación actualizada (serializador de lectura).
        """
        tx = self.get_object()
        self._guard_transfer_readonly(tx)
        serializer = TransactionActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = serializer.apply(tx)
        return Response(TransactionReadSerializer(updated).data, status=status.HTTP_200_OK)


class CategoryViewSet(viewsets.ModelViewSet):
    """CRUD de categorías del usuario (sin filtros de lectura especiales)."""

    serializer_class = CategorySerializer
    permission_classes = [IsOwner]

    def get_queryset(self):
        """Categorías del usuario autenticado."""
        return Category.objects.filter(user=self.request.user)


class ContactViewSet(viewsets.ModelViewSet):
    """CRUD de contactos (personas/entidades) del usuario."""

    serializer_class = ContactSerializer
    permission_classes = [IsOwner]

    def get_queryset(self):
        """Contactos del usuario autenticado."""
        return Contact.objects.filter(user=self.request.user)