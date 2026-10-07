"""serializers — CRM del negocio."""

from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from apps.core.currency import is_valid_amount, round_money
from apps.crm.tax_id import normalize_tax_id, tax_id_error
from apps.crm.models import (
    BusinessContact,
    CollectionFollowUp,
    Invoice,
    InvoiceItem,
    InvoicePayment,
    Order,
    OrderItem,
    OrderPayment,
    Product,
    ProductCategory,
)


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
        # Formato canónico PREFIJO-NÚMERO (V/J/E) y único por negocio.
        raw = (value or "").strip()
        if not raw:
            return ""
        tax_id = normalize_tax_id(raw)
        if not tax_id:
            raise serializers.ValidationError("Indica el tipo y el número de la cédula.")
        error = tax_id_error(tax_id)
        if error:
            raise serializers.ValidationError(error)
        request = self.context["request"]
        qs = BusinessContact.objects.filter(
            business__user=request.user, tax_id=tax_id
        )
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                "Ya existe un cliente con esta cédula/RIF."
            )
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
    """Serializador de líneas de factura (lectura)."""

    class Meta:
        model = InvoiceItem
        fields = ["id", "product", "description", "quantity", "unit_price", "discount", "total"]
        read_only_fields = ["id", "product", "total"]


class InvoiceItemWriteSerializer(serializers.ModelSerializer):
    """Serializador de líneas de factura en alta/edición.

    Acepta ``product`` del catálogo; si no se envía ``unit_price`` y hay
    producto, el precio se toma del catálogo según el tipo de cliente
    (ver ``InvoiceWriteSerializer.validate``).
    """

    product = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.all(), required=False
    )
    unit_price = serializers.DecimalField(
        max_digits=20, decimal_places=2, required=False
    )

    class Meta:
        model = InvoiceItem
        fields = ["product", "description", "quantity", "unit_price", "discount", "total"]
        read_only_fields = ["total"]

    def validate(self, attrs: dict) -> dict:
        quantity = attrs.get("quantity", 1)
        unit_price = attrs.get("unit_price", Decimal("0"))
        discount = attrs.get("discount", Decimal("0"))
        product = attrs.get("product")
        if quantity <= 0 or unit_price < 0:
            raise serializers.ValidationError(
                "La cantidad y el precio unitario deben ser positivos."
            )
        if product is None and attrs.get("unit_price") is None:
            raise serializers.ValidationError(
                "Indica un precio o un producto del catálogo."
            )
        if product is not None and product.user_id != self.context["request"].user.id:
            raise serializers.ValidationError(
                "El producto no pertenece a tu catálogo."
            )
        # Los productos contados «por unidad» solo admiten cantidades enteras.
        from apps.crm.services import requires_integer_amounts

        if (
            product is not None
            and requires_integer_amounts(product.unit)
            and quantity != quantity.to_integral_value()
        ):
            raise serializers.ValidationError(
                "Este producto se vende por unidad: la cantidad debe ser entera."
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
    latest_follow_up = serializers.SerializerMethodField()

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
            "latest_follow_up",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "business", "number", "created_at", "updated_at"]

    def get_latest_follow_up(self, obj) -> dict | None:
        """Resumen del seguimiento más reciente (prefetched en el viewset)."""
        rows = obj.follow_ups.all()[:1]
        if not rows:
            return None
        follow_up = rows[0]
        return {
            "id": str(follow_up.id),
            "channel": follow_up.channel,
            "outcome": follow_up.outcome,
            "promised_date": (
                serializers.DateField().to_representation(follow_up.promised_date)
                if follow_up.promised_date
                else None
            ),
            "notes": follow_up.notes,
            "created_at": serializers.DateTimeField().to_representation(
                follow_up.created_at
            ),
        }


class InvoiceWriteSerializer(serializers.ModelSerializer):
    """Serializador de alta/edición de facturas."""

    contact = serializers.PrimaryKeyRelatedField(queryset=BusinessContact.objects.none())
    items = InvoiceItemWriteSerializer(many=True)
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

        # Líneas sin precio explicitado pero con producto del catálogo: se toma
        # el precio según el tipo de cliente (mayorista → wholesale_price).
        contact = attrs.get("contact") or getattr(self.instance, "contact", None)
        for row in attrs.get("items", []):
            product = row.get("product")
            if product is not None and row.get("unit_price") is None and contact is not None:
                from apps.crm.services import _pick_unit_price

                unit_price = _pick_unit_price(product, contact)
                row["unit_price"] = unit_price
                row["total"] = round_money(
                    row["quantity"] * unit_price - row.get("discount", Decimal("0"))
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
                    product=row.get("product"),
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


class OrderItemSerializer(serializers.ModelSerializer):
    """Serializador de líneas de pedido (lectura)."""

    class Meta:
        model = OrderItem
        fields = [
            "id",
            "product",
            "new_product",
            "description",
            "quantity",
            "unit_price",
            "discount",
            "total",
        ]
        read_only_fields = ["id", "product", "new_product", "total"]


class OrderItemWriteSerializer(serializers.ModelSerializer):
    """Serializador de líneas de pedido en alta/edición.

    Cada línea refiere a un producto del inventario (``product``) o, en
    excluyente mutuo, a los datos de un producto nuevo (``new_product``) que se
    creará e integrará al inventario al recibir el pedido.
    """

    product = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.all(), required=False, allow_null=True
    )
    new_product = serializers.JSONField(required=False, write_only=True)
    description = serializers.CharField(required=False, allow_blank=True)
    unit_price = serializers.DecimalField(
        max_digits=20, decimal_places=2, required=False
    )

    class Meta:
        model = OrderItem
        fields = [
            "product",
            "new_product",
            "description",
            "quantity",
            "unit_price",
            "discount",
            "total",
        ]
        read_only_fields = ["total"]

    def validate(self, attrs: dict) -> dict:
        from apps.crm.services import _parse_new_product, requires_integer_amounts

        request = self.context["request"]
        product = attrs.get("product")
        new_product = attrs.get("new_product")
        if bool(product) == bool(new_product):
            raise serializers.ValidationError(
                "Indica un producto del inventario o los datos de un producto "
                "nuevo, no ambos."
            )

        quantity = attrs.get("quantity", Decimal("1"))
        discount = attrs.get("discount", Decimal("0"))
        description = attrs.get("description", "")
        unit: str = ""

        if new_product:
            data = _parse_new_product(dict(new_product))
            unit = data["unit"]
            description = description or data["name"]
            unit_price = attrs.get("unit_price")
            if unit_price is None:
                unit_price = Decimal(data.get("cost_price") or "0")
            else:
                unit_price = Decimal(str(unit_price))
            attrs["new_product"] = dict(data)
        else:
            if product.user_id != request.user.id:
                raise serializers.ValidationError(
                    "El producto no pertenece a tu catálogo."
                )
            description = description or product.name
            unit = product.unit
            unit_price = attrs.get("unit_price") or product.cost_price or Decimal("0")
            unit_price = Decimal(str(unit_price))

        attrs["description"] = description
        attrs["unit_price"] = unit_price

        if quantity <= 0 or unit_price < 0:
            raise serializers.ValidationError(
                "La cantidad y el precio unitario deben ser positivos."
            )
        if requires_integer_amounts(unit) and quantity != quantity.to_integral_value():
            raise serializers.ValidationError(
                "Este producto se cuenta por unidad: la cantidad debe ser entera."
            )
        attrs["total"] = round_money(quantity * unit_price - discount)
        return attrs


class OrderPaymentSerializer(serializers.ModelSerializer):
    """Serializador de pagos realizados contra un pedido."""

    class Meta:
        model = OrderPayment
        fields = ["id", "transaction_id", "amount", "paid_at", "note"]
        read_only_fields = ["id", "transaction_id", "paid_at"]


class OrderReadSerializer(serializers.ModelSerializer):
    """Serializador de lectura con proveedor, líneas y pagos anidados."""

    contact = BusinessContactSerializer(read_only=True)
    items = OrderItemSerializer(many=True, read_only=True)
    payments = OrderPaymentSerializer(many=True, read_only=True)
    payment_state = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "id",
            "business",
            "contact",
            "number",
            "order_date",
            "status",
            "payment_state",
            "subtotal",
            "shipping_amount",
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

    def get_payment_state(self, obj: Order) -> str:
        if obj.amount_paid <= 0:
            return "none"
        if obj.balance_due <= 0:
            return "paid"
        return "partial"


class OrderWriteSerializer(serializers.ModelSerializer):
    """Serializador de alta/edición de pedidos a proveedores."""

    contact = serializers.PrimaryKeyRelatedField(queryset=BusinessContact.objects.none())
    items = OrderItemWriteSerializer(many=True)
    order_date = serializers.DateField(required=False)
    shipping_amount = serializers.DecimalField(
        max_digits=20, decimal_places=2, required=False, default=Decimal("0")
    )
    paid_amount = serializers.DecimalField(
        max_digits=20, decimal_places=2, required=False, default=Decimal("0")
    )

    class Meta:
        model = Order
        fields = [
            "id",
            "business",
            "contact",
            "order_date",
            "shipping_amount",
            "paid_amount",
            "notes",
            "items",
        ]
        read_only_fields = ["id", "business"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = self.context["request"].user
        self.fields["contact"].queryset = BusinessContact.objects.filter(
            business__user=user, type__in=["proveedor", "ambos"]
        )

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("El pedido debe tener al menos una línea.")
        return value

    def validate_shipping_amount(self, value):
        if value is None:
            return Decimal("0")
        if value < 0:
            raise serializers.ValidationError("El envío no puede ser negativo.")
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

        contact = attrs.get("contact") or getattr(self.instance, "contact", None)
        if contact is not None and contact.business_id != business.id:
            raise serializers.ValidationError(
                {"contact": "El proveedor no pertenece a tu negocio."}
            )
        if contact is not None and contact.type not in ("proveedor", "ambos"):
            raise serializers.ValidationError(
                {"contact": "El contacto debe ser un proveedor."}
            )
        return attrs

    def create(self, validated_data: dict) -> Order:
        from apps.crm.services import create_order

        items = validated_data.pop("items")
        return create_order(
            user=self.context["request"].user,
            business=validated_data["business"],
            contact=validated_data["contact"],
            items_data=items,
            order_date=validated_data.get("order_date"),
            shipping_amount=validated_data.get("shipping_amount"),
            paid_amount=validated_data.get("paid_amount"),
            notes=validated_data.get("notes", ""),
        )

    def update(self, instance: Order, validated_data: dict) -> Order:
        """Permite editar solo pedidos en borrador; reemplaza las líneas."""
        if instance.status != "borrador":
            raise serializers.ValidationError(
                {"status": "Solo se pueden editar pedidos en borrador."}
            )

        items = validated_data.pop("items", None)
        instance.contact = validated_data.get("contact", instance.contact)
        instance.order_date = validated_data.get("order_date", instance.order_date)
        instance.shipping_amount = validated_data.get(
            "shipping_amount", instance.shipping_amount
        )
        instance.notes = validated_data.get("notes", instance.notes)

        if items is not None:
            instance.items.all().delete()
            subtotal = Decimal("0")
            for row in items:
                subtotal += row["total"]
                OrderItem.objects.create(
                    user=instance.user,
                    order=instance,
                    product=row.get("product"),
                    new_product=row.get("new_product") or {},
                    description=row["description"],
                    quantity=row["quantity"],
                    unit_price=row["unit_price"],
                    discount=row.get("discount", Decimal("0")),
                    total=row["total"],
                )
            instance.subtotal = round_money(subtotal)
            instance.total = round_money(instance.subtotal + instance.shipping_amount)
            instance.balance_due = instance.total
            instance.status = "borrador"

        instance.save()
        return instance


class CollectionFollowUpSerializer(serializers.ModelSerializer):
    """Serializador de seguimientos de cobranza.

    Solo admite lectura, alta y borrado (los registros no se editan: si hubo
    un error se eliminan y se crea uno nuevo).
    """

    class Meta:
        model = CollectionFollowUp
        fields = [
            "id",
            "invoice",
            "channel",
            "outcome",
            "promised_date",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = self.context["request"].user
        self.fields["invoice"].queryset = Invoice.objects.filter(business__user=user)

    def validate(self, attrs: dict) -> dict:
        outcome = attrs.get("outcome")
        promised_date = attrs.get("promised_date")
        if outcome == "promesa_pago" and not promised_date:
            raise serializers.ValidationError(
                {"promised_date": "Una promesa de pago requiere fecha comprometida."}
            )
        return attrs

    def create(self, validated_data: dict) -> CollectionFollowUp:
        request = self.context["request"]
        validated_data["user_id"] = request.user.id
        return super().create(validated_data)


class ProductCategorySerializer(serializers.ModelSerializer):
    """Serializador de categorías de producto."""

    class Meta:
        model = ProductCategory
        fields = ["id", "business", "name"]
        read_only_fields = ["id", "business"]

    def validate_name(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError("El nombre no puede estar vacío.")
        return value

    def create(self, validated_data: dict) -> ProductCategory:
        from apps.business.models import Business

        request = self.context["request"]
        try:
            business = Business.objects.get(user=request.user)
        except Business.DoesNotExist:
            raise serializers.ValidationError(
                {"business": "No tienes un negocio creado."}
            )
        validated_data["user_id"] = request.user.id
        validated_data["business"] = business
        return super().create(validated_data)


class ProductSerializer(serializers.ModelSerializer):
    """Serializador de productos del inventario.

    ``is_low_stock`` informa si queda por debajo del umbral de alerta. Las
    existencias no se editan a través del CRUD: cualquier movimiento se hace
    con el endpoint ``adjust`` para quedar auditado en ``StockAdjustment``.
    """

    category = serializers.PrimaryKeyRelatedField(
        queryset=ProductCategory.objects.none(), required=False, allow_null=True
    )
    supplier = serializers.PrimaryKeyRelatedField(
        queryset=BusinessContact.objects.none(), required=False, allow_null=True
    )
    stock_quantity = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False
    )
    is_low_stock = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "business",
            "name",
            "sku",
            "description",
            "unit",
            "unit_price",
            "wholesale_price",
            "cost_price",
            "category",
            "supplier",
            "stock_quantity",
            "low_stock_threshold",
            "is_active",
            "is_low_stock",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "business", "created_at", "updated_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = self.context["request"].user
        self.fields["category"].queryset = ProductCategory.objects.filter(
            business__user=user
        )
        self.fields["supplier"].queryset = BusinessContact.objects.filter(
            business__user=user, type__in=["proveedor", "ambos"]
        ).select_related("business")

    def get_is_low_stock(self, obj: Product) -> bool:
        if obj.low_stock_threshold is None:
            return False
        return obj.stock_quantity <= obj.low_stock_threshold

    def validate_name(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError("El nombre no puede estar vacío.")
        return value

    def validate_sku(self, value: str) -> str:
        return value.strip()

    def _non_negative(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError("El valor no puede ser negativo.")
        return value

    def validate_unit_price(self, value):
        return self._non_negative(value)

    def validate_wholesale_price(self, value):
        return self._non_negative(value)

    def validate_cost_price(self, value):
        return self._non_negative(value)

    def validate_low_stock_threshold(self, value):
        return self._non_negative(value)

    def validate(self, attrs: dict) -> dict:
        # Regla de redondez: con la unidad «Unidad» las cantidades se manejan
        # en enteros (existencias y umbral de alerta). En alta, adelante; en
        # edición, se usa la unidad que quede vigente tras el cambio.
        from apps.crm.services import requires_integer_amounts

        unit = attrs.get("unit")
        if unit is None and self.instance is not None:
            unit = self.instance.unit
        if not requires_integer_amounts(unit or ""):
            return attrs

        message = "Con la unidad «Unidad» las cantidades deben ser enteras (sin decimales)."
        errors: dict = {}
        for field in ("stock_quantity", "low_stock_threshold"):
            value = attrs.get(field)
            if value is not None and value != value.to_integral_value():
                errors[field] = message
        # kg → unidad con existencias ya decimales: se pide entero previo.
        if (
            self.instance is not None
            and attrs.get("unit") == "unidad"
            and self.instance.unit != "unidad"
            and self.instance.stock_quantity != self.instance.stock_quantity.to_integral_value()
        ):
            errors.setdefault(
                "unit",
                "Este producto tiene existencias con decimales. Ajústalas a un "
                "entero antes de cambiar a la unidad «Unidad».",
            )
        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    def create(self, validated_data: dict) -> Product:
        from apps.business.models import Business

        request = self.context["request"]
        try:
            business = Business.objects.get(user=request.user)
        except Business.DoesNotExist:
            raise serializers.ValidationError(
                {"business": "No tienes un negocio creado."}
            )
        validated_data["user_id"] = request.user.id
        validated_data["business"] = business
        return super().create(validated_data)

    def update(self, instance: Product, validated_data: dict) -> Product:
        # Las existencias solo cambian por el endpoint de ajuste (auditoría).
        validated_data.pop("stock_quantity", None)
        return super().update(instance, validated_data)
