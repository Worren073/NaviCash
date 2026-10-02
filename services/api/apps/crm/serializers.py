"""serializers — CRM del negocio."""

from __future__ import annotations

from rest_framework import serializers

from apps.core.currency import is_valid_amount
from apps.crm.models import BusinessContact


class BusinessContactSerializer(serializers.ModelSerializer):
    """Serializador de clientes/proveedores del negocio."""

    class Meta:
        model = BusinessContact
        fields = [
            "id",
            "business",
            "name",
            "email",
            "phone",
            "address",
            "tax_id",
            "type",
            "customer_type",
            "payment_terms_days",
            "credit_limit",
            "currency",
            "notes",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "business", "created_at", "updated_at"]

    def validate_name(self, value: str) -> str:
        name = value.strip()
        if not name:
            raise serializers.ValidationError("El nombre es obligatorio.")
        return name

    def validate_payment_terms_days(self, value: int) -> int:
        if value < 0:
            raise serializers.ValidationError("Los días de crédito no pueden ser negativos.")
        return value

    def validate_credit_limit(self, value):
        if value is not None and not is_valid_amount(value):
            raise serializers.ValidationError("El límite de crédito debe ser mayor a 0.")
        return value

    def validate_tax_id(self, value: str) -> str:
        tax_id = value.strip()
        if not tax_id:
            return tax_id
        request = self.context["request"]
        qs = BusinessContact.objects.filter(
            business__user=request.user, tax_id=tax_id
        )
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Ya existe un contacto con este RIF/NIT.")
        return tax_id

    def validate(self, attrs: dict) -> dict:
        type_value = attrs.get("type", getattr(self.instance, "type", "cliente"))
        customer_type = attrs.get("customer_type", "")
        if customer_type and type_value == "proveedor":
            raise serializers.ValidationError(
                {"customer_type": "El tipo de cliente no aplica a proveedores."}
            )
        return attrs

    def create(self, validated_data: dict) -> BusinessContact:
        request = self.context["request"]
        validated_data["user_id"] = request.user.id
        if "business" not in validated_data:
            # El negocio se infiere del usuario autenticado (un negocio por usuario).
            from apps.business.models import Business

            try:
                business = Business.objects.get(user=request.user)
            except Business.DoesNotExist:
                raise serializers.ValidationError(
                    {"business": "No tienes un negocio creado."}
                )
            validated_data["business"] = business
        return super().create(validated_data)
