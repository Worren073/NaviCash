"""serializers — Serializadores de ``transactions``.

- ``TransactionSerializer``: crea/actualiza operaciones recalculando la
  conversión USD y, si se guarda como "pagado", ajusta la billetera.
- ``TransactionActionSerializer``: recibe un estado (pagado/cancelado/...) y
  delega en ``set_state``.
- ``CategorySerializer`` / ``ContactSerializer``: CRUD simple.
"""

from __future__ import annotations

from rest_framework import serializers

from apps.core.currency import is_valid_amount
from apps.transactions.models import Category, Contact, Transaction
from apps.wallets.models import Wallet
from apps.transactions.services import (
    _apply_to_wallet,
    compute_usd_equivalent,
    mark_paid,
    set_state,
)


class CategorySerializer(serializers.ModelSerializer):
    """Serializador de categorías (owner-scoped)."""

    class Meta:
        model = Category
        fields = ["id", "name", "icon", "tipo", "is_default"]
        read_only_fields = ["id", "is_default"]

    def create(self, validated_data: dict) -> Category:
        """Crea la categoría ligada al usuario autenticado."""
        validated_data["user_id"] = self.context["request"].user.id
        return super().create(validated_data)


class ContactSerializer(serializers.ModelSerializer):
    """Serializador de contactos (owner-scoped)."""

    class Meta:
        model = Contact
        fields = ["id", "name", "note"]

    def create(self, validated_data: dict) -> Contact:
        """Crea el contacto ligado al usuario autenticado."""
        validated_data["user_id"] = self.context["request"].user.id
        return super().create(validated_data)


class TransactionWriteSerializer(serializers.ModelSerializer):
    """Serializador de alta/edición de operaciones.

    - Recalcula la conversión a USD al guardar (no admite valores de
      ``monto_usd``/``tasa_usd`` del cliente).
    - Si la operación se crea directamente como "pagado", ajusta la billetera.
    - Validaciones de negocio: monto > 0, billetera propia y de la misma
      moneda, fechas coherentes.
    """

    monto = serializers.DecimalField(max_digits=20, decimal_places=2)
    wallet = serializers.PrimaryKeyRelatedField(
        queryset=Wallet.objects.none(), required=False, allow_null=True
    )
    category = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.none(), required=False, allow_null=True
    )
    contact = serializers.PrimaryKeyRelatedField(
        queryset=Contact.objects.none(), required=False, allow_null=True
    )

    class Meta:
        model = Transaction
        fields = [
            "id",
            "tipo",
            "estado",
            "monto",
            "moneda",
            "concepto",
            "contact",
            "category",
            "wallet",
            "fecha",
            "fecha_vencimiento",
            "remind_me",
            "nota",
            "monto_usd",  # solo lectura de detalle
            "tasa_usd",   # solo lectura de detalle
            "fuente_tasa",  # solo lectura de detalle
            "created_at",
        ]
        read_only_fields = ["monto_usd", "tasa_usd", "fuente_tasa", "created_at", "id"]

    def __init__(self, *args, **kwargs):
        """Acota las querysets de relaciones al usuario de la request."""
        super().__init__(*args, **kwargs)
        user = self.context["request"].user
        self.fields["wallet"].queryset = Wallet.objects.filter(user=user).all()
        self.fields["category"].queryset = Category.objects.filter(user=user).all()
        self.fields["contact"].queryset = Contact.objects.filter(user=user).all()

    def validate_monto(self, value):
        """El monto debe ser una cantidad válida (>= 0.01)."""
        if not is_valid_amount(value):
            raise serializers.ValidationError("El monto debe ser mayor a 0.01.")
        return value

    def validate(self, attrs: dict) -> dict:
        """Valida coherencia entre billetera, moneda y fechas."""
        wallet = attrs.get("wallet")
        if wallet:
            if wallet.user_id != self.context["request"].user.id:
                raise serializers.ValidationError({"wallet": "Billetera no válida."})
            if wallet.currency != attrs.get("moneda", getattr(self.instance, "moneda", None)):
                raise serializers.ValidationError(
                    {"wallet": "La billetera debe usar la misma moneda que la operación."}
                )
        fecha = attrs.get("fecha") or getattr(self.instance, "fecha", None)
        vencimiento = attrs.get("fecha_vencimiento")
        if vencimiento and fecha and vencimiento < fecha:
            raise serializers.ValidationError(
                {"fecha_vencimiento": "El vencimiento no puede ser anterior a la fecha."}
            )
        return attrs

    def create(self, validated_data: dict) -> Transaction:
        """Crea la operación con su conversión USD congelada y estado."""
        user = self.context["request"].user
        requested_state = validated_data.pop("estado", "pendiente")

        monto = validated_data["monto"]
        moneda = validated_data["moneda"]
        validated_data.update(compute_usd_equivalent(monto, moneda))

        # Siempre se persiste como pendiente; el servicio ``mark_paid`` aplica
        # el estado y el efecto de saldo de forma atómica si corresponde.
        tx = Transaction.objects.create(user=user, estado="pendiente", **validated_data)

        if requested_state == "pagado":
            mark_paid(tx)

        return tx

    def update(self, instance: Transaction, validated_data: dict) -> Transaction:
        """Actualiza la operación y reconcilia la billetera si cambió el estado.

        Estrategia (dentro de una transacción atómica):
        1. Se revierte el efecto de saldo de la versión anterior si estaba pagada.
        2. Se recalculan monto/tasa USD si cambió cantidad o moneda.
        3. Se guarda como pendiente y, si se solicita ``pagado``, se aplica la
           transición vía ``set_state`` (que vuelve a aplicar el efecto).
        """
        from django.db import transaction as db_transaction

        with db_transaction.atomic():
            was_paid = instance.estado == "pagado"
            requested_state = validated_data.pop("estado", instance.estado)

            if was_paid and instance.wallet:
                _apply_to_wallet(instance, reverse=True)

            if "monto" in validated_data or "moneda" in validated_data:
                monto = validated_data.get("monto", instance.monto)
                moneda = validated_data.get("moneda", instance.moneda)
                validated_data.update(compute_usd_equivalent(monto, moneda))

            for attr, value in validated_data.items():
                setattr(instance, attr, value)

            instance.estado = "pendiente"
            instance.fecha_pagado = None
            instance.save()

            # Se aplica la transición solicitada (vuelve a pagar con el nuevo monto).
            if requested_state != "pendiente":
                set_state(instance, requested_state)

        return instance


class TransactionReadSerializer(serializers.ModelSerializer):
    """Serializador de lectura con el estado efectivo (incluye 'retrasado')."""

    effective_state = serializers.CharField(read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)
    wallet_name = serializers.CharField(source="wallet.name", read_only=True, default=None)

    class Meta:
        model = Transaction
        fields = [
            "id",
            "tipo",
            "estado",
            "effective_state",
            "is_overdue",
            "monto",
            "moneda",
            "monto_usd",
            "tasa_usd",
            "fuente_tasa",
            "concepto",
            "contact",
            "category",
            "wallet",
            "wallet_name",
            "fecha",
            "fecha_vencimiento",
            "fecha_pagado",
            "remind_me",
            "nota",
            "created_at",
        ]


class TransactionActionSerializer(serializers.Serializer):
    """Recibe una acción de estado: ``{"estado": "pagado|cancelado|pendiente"}``."""

    estado = serializers.ChoiceField(choices=["pagado", "cancelado", "pendiente"])

    def apply(self, instance: Transaction) -> Transaction:
        """Aplica la transición usando ``set_state``.

        Args:
            instance: operación a mutar.

        Returns:
            La operación actualizada.

        Raises:
            BusinessRuleError: si la transición no es válida.
        """
        return set_state(instance, self.validated_data["estado"])