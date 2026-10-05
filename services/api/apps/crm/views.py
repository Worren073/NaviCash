"""views — CRM del negocio."""

from __future__ import annotations

from decimal import Decimal, DecimalException

from django.db import IntegrityError, transaction
from django.db.models import Prefetch, Q
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.core.permissions import IsOwner
from apps.crm.models import (
    BusinessContact,
    CollectionFollowUp,
    Invoice,
    Product,
    ProductCategory,
    StockAdjustment,
)
from apps.crm.services import GOODS_OUT_STATUSES, requires_integer_amounts
from apps.crm.tax_id import tax_id_search_term
from apps.crm.serializers import (
    BusinessContactSerializer,
    CollectionFollowUpSerializer,
    InvoiceReadSerializer,
    InvoiceWriteSerializer,
    ProductCategorySerializer,
    ProductSerializer,
)


class BusinessContactViewSet(viewsets.ModelViewSet):
    """CRUD de clientes y proveedores del negocio."""

    serializer_class = BusinessContactSerializer
    permission_classes = [IsOwner]

    def get_queryset(self):
        """Contactos del usuario autenticado, con búsqueda opcional."""
        qs = BusinessContact.objects.filter(user=self.request.user).select_related("business")
        search = self.request.query_params.get("search")
        if search:
            # La búsqueda por cédula tolera el prefijo suelto: "v1234" y
            # "V-1234" encuentran el mismo contacto.
            qs = qs.filter(
                Q(name__icontains=search)
                | Q(email__icontains=search)
                | Q(phone__icontains=search)
                | Q(tax_id__icontains=search)
                | Q(tax_id__icontains=tax_id_search_term(search))
            )
        type_filter = self.request.query_params.get("type")
        if type_filter:
            qs = qs.filter(type=type_filter)
        return qs.order_by("name")


class InvoiceViewSet(viewsets.ModelViewSet):
    """Facturación y cuentas por cobrar del negocio."""

    permission_classes = [IsOwner]
    filterset_fields = ["status"]

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return InvoiceWriteSerializer
        return InvoiceReadSerializer

    def get_queryset(self):
        """Facturas del usuario, con búsqueda y filtros opcionales."""
        qs = (
            Invoice.objects.filter(user=self.request.user)
            .select_related("business", "contact")
            .prefetch_related(
                "items",
                "payments",
                Prefetch(
                    "follow_ups",
                    queryset=CollectionFollowUp.objects.order_by("-created_at"),
                ),
            )
        )
        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(
                Q(number__icontains=search) | Q(contact__name__icontains=search)
            )
        inv_status = self.request.query_params.get("status")
        if inv_status:
            qs = qs.filter(status=inv_status)
        return qs.order_by("-issue_date")

    def _read_response(self, instance, status_code: int = 200):
        """Serializa con el serializer de lectura (más campos computados)."""
        serializer = InvoiceReadSerializer(
            instance, context=self.get_serializer_context()
        )
        return Response(serializer.data, status=status_code)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return self._read_response(serializer.instance, status_code=201)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return self._read_response(serializer.instance)

    def perform_destroy(self, instance: Invoice):
        """Impide borrar facturas con pagos (integridad de cobranza).

        Al borrar una factura sin pagos que ya descontó existencias se repone
        el stock (la anulación es la operación formal; el borrado es un atajo).
        """
        if instance.payments.exists():
            from rest_framework.exceptions import ValidationError

            raise ValidationError("No se puede borrar una factura con pagos registrados.")
        if instance.status in GOODS_OUT_STATUSES:
            from apps.crm.services import _restore_stock

            _restore_stock(instance)
        instance.delete()

    @action(detail=True, methods=["post"])
    def send(self, request, pk=None):
        """Envía una factura en borrador (borrador → enviada)."""
        invoice = self.get_object()
        from apps.crm.services import send_invoice

        send_invoice(invoice)
        return Response(self.get_serializer(invoice).data)

    @action(detail=True, methods=["post"])
    def pay(self, request, pk=None):
        """Registra un pago contra la factura; crea el cobro en la billetera."""
        invoice = self.get_object()
        from apps.crm.services import record_invoice_payment

        amount = request.data.get("amount")
        if not amount:
            return Response(
                {"detail": "Debes indicar el monto del pago.", "code": "validation_error"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        record_invoice_payment(
            invoice,
            Decimal(str(amount)),
            note=request.data.get("note", ""),
        )
        return Response(self.get_serializer(invoice).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        """Anula la factura (congela el documento, no revierte pagos)."""
        invoice = self.get_object()
        from apps.crm.services import cancel_invoice

        cancel_invoice(invoice)
        return Response(self.get_serializer(invoice).data)


class CollectionFollowUpViewSet(viewsets.ModelViewSet):
    """Seguimientos de cobranza del negocio (solo lectura, alta y borrado)."""

    serializer_class = CollectionFollowUpSerializer
    permission_classes = [IsOwner]
    http_method_names = ["get", "post", "delete", "head", "options"]

    def get_queryset(self):
        """Seguimientos del usuario, filtrables por factura."""
        qs = CollectionFollowUp.objects.filter(user=self.request.user).select_related(
            "invoice", "invoice__contact"
        )
        invoice_id = self.request.query_params.get("invoice")
        if invoice_id:
            qs = qs.filter(invoice_id=invoice_id)
        return qs.order_by("-created_at")


class ProductCategoryViewSet(viewsets.ModelViewSet):
    """CRUD de categorías de producto."""

    serializer_class = ProductCategorySerializer
    permission_classes = [IsOwner]

    def get_queryset(self):
        return ProductCategory.objects.filter(user=self.request.user).order_by("name")

    def create(self, request, *args, **kwargs):
        try:
            return super().create(request, *args, **kwargs)
        except IntegrityError:
            raise ValidationError(
                {"name": "Ya tienes una categoría con ese nombre."}
            )


class ProductViewSet(viewsets.ModelViewSet):
    """CRUD del inventario, con ajuste de existencias auditado."""

    serializer_class = ProductSerializer
    permission_classes = [IsOwner]

    def get_queryset(self):
        """Productos del usuario, con búsqueda y filtros de categoría/activo."""
        qs = Product.objects.filter(user=self.request.user).select_related(
            "category", "supplier"
        )
        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(sku__icontains=search))
        category = self.request.query_params.get("category")
        if category:
            qs = qs.filter(category_id=category)
        active = self.request.query_params.get("active")
        if active in ("true", "false"):
            qs = qs.filter(is_active=active == "true")
        return qs.order_by("name")

    def create(self, request, *args, **kwargs):
        try:
            return super().create(request, *args, **kwargs)
        except IntegrityError:
            raise ValidationError(
                {
                    "detail": "Ya tienes un producto con ese nombre o código (SKU) "
                    "en este negocio."
                }
            )

    def update(self, request, *args, **kwargs):
        try:
            return super().update(request, *args, **kwargs)
        except IntegrityError:
            raise ValidationError(
                {
                    "detail": "Ya tienes un producto con ese nombre o código (SKU) "
                    "en este negocio."
                }
            )

    @action(detail=True, methods=["post"])
    def adjust(self, request, pk=None):
        """Ajusta existencias de forma auditada ({delta, reason}).

        ``delta`` es un número con signo (p.ej. `+5` entrada, `-2` salida).
        """
        product = self.get_object()
        delta = request.data.get("delta")
        if delta is None:
            return Response(
                {"detail": "Debes indicar el delta del ajuste.", "code": "validation_error"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            delta = Decimal(str(delta))
        except (TypeError, ValueError, DecimalException):
            return Response(
                {"detail": "El delta debe ser un número.", "code": "validation_error"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # Con la unidad «Unidad» las existencias se manejan en enteros.
        if requires_integer_amounts(product.unit) and delta != delta.to_integral_value():
            return Response(
                {
                    "detail": "Este producto se cuenta por unidad: el ajuste debe ser entero.",
                    "code": "validation_error",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        reason = str(request.data.get("reason", "")).strip()
        if not reason:
            return Response(
                {"detail": "Indica un motivo para el ajuste.", "code": "validation_error"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # El cambio de stock y su registro caen en la misma transacción y la
        # fila del producto queda bloqueada: dos ajustes simultáneos nunca se
        # pisan (mismo esquema que _withdraw_stock en services).
        with transaction.atomic():
            product = Product.objects.select_for_update().get(pk=product.pk)
            new_stock = product.stock_quantity + delta
            if new_stock < 0:
                return Response(
                    {
                        "detail": f"El stock no puede quedar negativo (hay {product.stock_quantity}).",
                        "code": "validation_error",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            product.stock_quantity = new_stock
            product.save(update_fields=["stock_quantity", "updated_at"])
            StockAdjustment.objects.create(
                user=request.user, product=product, delta=delta, reason=reason
            )
        return Response(self.get_serializer(product).data)
