"""serializers — Serializadores de ``checklists``.

- ``ChecklistItemSerializer``: producto con precio por unidad, cantidad y
  subtotal calculado. ``id`` es escribible para sincronizar (diff) los ítems
  de una lista completa enviada por el cliente.
- ``ShoppingListSerializer``: lista con sus ítems anidados y los derivados de
  lectura (total estimado, progreso). Los campos que solo se fijan al completar
  (``estado``, ``wallet``, ``total_real``, ``completed_at``) son de solo lectura.
- ``ChecklistCompleteSerializer``: recibe la cuenta de pago y el total real.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from rest_framework import serializers

from apps.checklists.models import ListItem, ShoppingList
from apps.core.currency import is_valid_amount
from apps.wallets.models import Wallet


class ChecklistItemSerializer(serializers.ModelSerializer):
    """Producto de una lista de compras."""

    id = serializers.UUIDField(read_only=False, required=False, allow_null=True)
    subtotal = serializers.DecimalField(max_digits=20, decimal_places=2, read_only=True)

    class Meta:
        model = ListItem
        fields = ["id", "name", "precio_unitario", "cantidad", "is_checked", "subtotal", "created_at"]
        read_only_fields = ["created_at"]

    def validate(self, attrs: dict) -> dict:
        """Un producto marcado debe tener precio de unidad registrado (modal)."""
        is_checked = attrs.get("is_checked", getattr(self.instance, "is_checked", False))
        precio = attrs.get("precio_unitario", getattr(self.instance, "precio_unitario", None))
        cantidad = attrs.get("cantidad", getattr(self.instance, "cantidad", 1))
        if is_checked and precio is None:
            raise serializers.ValidationError(
                {"precio_unitario": "Registra el precio por unidad antes de marcar el producto."}
            )
        if cantidad < 1:
            raise serializers.ValidationError(
                {"cantidad": "La cantidad debe ser al menos 1."}
            )
        return attrs


class ShoppingListSerializer(serializers.ModelSerializer):
    """Lista de compras con sus productos y los derivados de lectura."""

    items = ChecklistItemSerializer(many=True, required=False, allow_empty=True)
    total_estimado = serializers.DecimalField(max_digits=20, decimal_places=2, read_only=True)
    progress_percent = serializers.DecimalField(max_digits=6, decimal_places=1, read_only=True)
    wallet_name = serializers.CharField(source="wallet.name", read_only=True, default=None)

    class Meta:
        model = ShoppingList
        fields = [
            "id",
            "name",
            "currency",
            "estado",
            "total_estimado",
            "progress_percent",
            "total_real",
            "wallet",
            "wallet_name",
            "transaction",
            "completed_at",
            "items",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "estado",
            "total_real",
            "wallet",
            "wallet_name",
            "transaction",
            "completed_at",
            "created_at",
        ]

    def validate(self, attrs: dict) -> dict:
        """Una lista completada no se edita y la moneda no se puede cambiar."""
        if self.instance:
            if self.instance.estado == "completada":
                raise serializers.ValidationError(
                    "La lista ya está completada; no se puede editar."
                )
            if "currency" in attrs and attrs["currency"] != self.instance.currency:
                raise serializers.ValidationError(
                    {"currency": "No puedes cambiar la moneda de una lista existente."}
                )
        return attrs

    def create(self, validated_data: dict) -> ShoppingList:
        """Crea la lista con sus productos ligada al usuario autenticado."""
        items_data = validated_data.pop("items", [])
        validated_data["user_id"] = self.context["request"].user.id
        shopping_list = ShoppingList.objects.create(**validated_data)
        self._sync_items(shopping_list, items_data)
        return shopping_list

    def update(self, instance: ShoppingList, validated_data: dict) -> ShoppingList:
        """Actualiza la lista y sincroniza sus productos (diff por id)."""
        items_data = validated_data.pop("items", None)
        if items_data is not None:
            with transaction.atomic():
                self._sync_items(instance, items_data)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save(update_fields=list(validated_data) + ["updated_at"])
        return instance

    def _sync_items(self, shopping_list: ShoppingList, items_data: list) -> None:
        """Aplica el set de ítems: actualiza por id, crea los nuevos, borra los ausentes."""
        existing = {str(item.id): item for item in shopping_list.items.all()}
        keep = set()
        user = self.context["request"].user
        for item_data in items_data:
            item_id = item_data.pop("id", None)
            if item_id and str(item_id) in existing:
                item = existing[str(item_id)]
                for attr, value in item_data.items():
                    setattr(item, attr, value)
                item.save()
                keep.add(str(item_id))
            else:
                item_data["user_id"] = user.id
                ListItem.objects.create(checklist=shopping_list, **item_data)
        for item_id, item in existing.items():
            if item_id not in keep:
                item.delete()


class ChecklistCompleteSerializer(serializers.Serializer):
    """Cierre de la lista: cuenta de pago y total real (editable).

    El ``total_real`` sustituye al estimado: en el mercado se paga lo que marca
    la caja, no la suma de los subtotales. La cuenta debe ser propia y de la
    misma moneda de la lista (se valida en el servicio).
    """

    wallet = serializers.PrimaryKeyRelatedField(queryset=Wallet.objects.none())
    total_real = serializers.DecimalField(max_digits=20, decimal_places=2)

    def __init__(self, *args, **kwargs):
        """Acota las cuentas al usuario de la request."""
        super().__init__(*args, **kwargs)
        user = self.context["request"].user
        self.fields["wallet"].queryset = Wallet.objects.filter(user=user).all()

    def validate_total_real(self, value) -> Decimal:
        """El total pagado debe ser una cantidad válida (>= 0.01)."""
        if not is_valid_amount(value):
            raise serializers.ValidationError("El total pagado debe ser mayor a 0.01.")
        return value