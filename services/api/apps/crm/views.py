"""views — CRM del negocio."""

from __future__ import annotations

from decimal import Decimal

from django.db.models import Prefetch, Q
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.permissions import IsOwner
from apps.crm.models import BusinessContact, CollectionFollowUp, Invoice
from apps.crm.serializers import (
    BusinessContactSerializer,
    CollectionFollowUpSerializer,
    InvoiceReadSerializer,
    InvoiceWriteSerializer,
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
            qs = qs.filter(
                Q(name__icontains=search)
                | Q(email__icontains=search)
                | Q(phone__icontains=search)
                | Q(tax_id__icontains=search)
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
        """Impide borrar facturas con pagos (integridad de cobranza)."""
        if instance.payments.exists():
            from rest_framework.exceptions import ValidationError

            raise ValidationError("No se puede borrar una factura con pagos registrados.")
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
