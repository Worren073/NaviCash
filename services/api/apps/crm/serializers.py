"""serializers — CRM del negocio."""

from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from apps.core.currency import is_valid_amount, round_money
from apps.crm.models import BusinessContact, Invoice, InvoiceItem, InvoicePayment


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


class InvoiceItemSerializer(serializers.ModelSerializer):
    """Serializador de líneas de factura (lectura y escritura)."""

    class Meta:
        model = InvoiceItem
        fields = ["id", "description", "quantity", "unit_price", "discount", "total"]
        read_only_fields = ["id", "total"]

    def validate(self, attrs: dict) -> dict:
        quantity = attrs.get("quantity", 1)
        unit_price = attrs.get("unit_price", Decimal("0"))
        discount = attrs.get("discount", Decimal("0"))
        if quantity <= 0 or unit_price < 0:
            raise serializers.ValidationError(
                "La cantidad y el precio unitario deben ser positivos."
            )
        attrs["total"] = quantity * unit_price - discount
        return attrs


class InvoicePaymentSerializer(serializers.ModelSerializer):
    """Serializador de pagos recibidos contra una factura."""

    class Meta:
        model = InvoicePayment
        fields = ["id", "transaction_id", "amount", "paid_at", "note"]
        read_only_fields = ["id", "transaction_id", "paid_at"]


class InvoiceReadSerializer(serializers.ModelSerializer):
    """Serializador de lectura con contacto, líneas y pagos anidados."""

    contact = BusinessContactSerializer(read_only=True)
    items = InvoiceItemSerializer(many=True, read_only=True)
    payments = InvoicePaymentSerializer(many=True, read_only=True)

    class Meta:
        model = Invoice
        fields = [
            "id",
            "business",
            "contact",
            "number",
            "issue_date",
            "due_date",
            "status",
            "subtotal",
            "tax_amount",
            "total",
            "amount_paid",
            "balance_due",
            "currency",
            "notes",
            "items",
            "payments",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "business", "number", "created_at", "updated_at"]


class InvoiceWriteSerializer(serializers.ModelSerializer):
    """Serializador de alta/edición de facturas."""

    contact = serializers.PrimaryKeyRelatedField(queryset=BusinessContact.objects.none())
    items = InvoiceItemSerializer(many=True)
    issue_date = serializers.DateField(required=False)
    due_date = serializers.DateField(required=False)
    paid_amount = serializers.DecimalField(
        max_digits=20, decimal_places=2, required=False, default=Decimal("0")
    )

    class Meta:
        model = Invoice
        fields = [
            "id",
            "business",
            "contact",
            "issue_date",
            "due_date",
            "tax_amount",
            "paid_amount",
            "notes",
            "items",
        ]
        read_only_fields = ["id", "business"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = self.context["request"].user
        self.fields["contact"].queryset = BusinessContact.objects.filter(
            business__user=user
        )

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("La factura debe tener al menos una línea.")
        return value

    def validate_tax_amount(self, value):
        if value is None:
            return Decimal("0")
        if value < 0:
            raise serializers.ValidationError("El impuesto no puede ser negativo.")
        return value

    def validate_paid_amount(self, value):
        if value is None:
            return Decimal("0")
        if value < 0:
            raise serializers.ValidationError("El monto pagado no puede ser negativo.")
        return value

    def validate(self, attrs: dict) -> dict:
        from apps.business.models import Business

        request = self.context["request"]
        try:
            business = Business.objects.get(user=request.user)
        except Business.DoesNotExist:
            raise serializers.ValidationError(
                {"business": "No tienes un negocio creado."}
            )
        attrs["business"] = business

        issue_date = attrs.get("issue_date")
        due_date = attrs.get("due_date")
        if due_date and issue_date and due_date < issue_date:
            raise serializers.ValidationError(
                {"due_date": "El vencimiento no puede ser anterior a la emisión."}
            )
        return attrs

    def create(self, validated_data: dict) -> Invoice:
        from apps.crm.services import create_invoice

        items = validated_data.pop("items")
        return create_invoice(
            user=self.context["request"].user,
            business=validated_data["business"],
            contact=validated_data["contact"],
            items_data=items,
            issue_date=validated_data.get("issue_date"),
            due_date=validated_data.get("due_date"),
            tax_amount=validated_data.get("tax_amount"),
            paid_amount=validated_data.get("paid_amount"),
            notes=validated_data.get("notes", ""),
        )

    def update(self, instance: Invoice, validated_data: dict) -> Invoice:
        """Permite editar solo facturas en borrador; reemplaza las líneas."""
        if instance.status != "borrador":
            raise serializers.ValidationError(
                {"status": "Solo se pueden editar facturas en borrador."}
            )

        items = validated_data.pop("items", None)
        instance.contact = validated_data.get("contact", instance.contact)
        instance.issue_date = validated_data.get("issue_date", instance.issue_date)
        instance.due_date = validated_data.get("due_date", instance.due_date)
        instance.tax_amount = validated_data.get("tax_amount", instance.tax_amount)
        instance.notes = validated_data.get("notes", instance.notes)

        if items is not None:
            instance.items.all().delete()
            subtotal = Decimal("0")
            for row in items:
                subtotal += row["total"]
                InvoiceItem.objects.create(
                    user=instance.user,
                    invoice=instance,
                    description=row["description"],
                    quantity=row["quantity"],
                    unit_price=row["unit_price"],
                    discount=row.get("discount", Decimal("0")),
                    total=row["total"],
                )
            instance.subtotal = round_money(subtotal)
            instance.total = round_money(instance.subtotal + instance.tax_amount)
            instance.balance_due = instance.total
            instance.status = "borrador"

        instance.save()
        return instance
