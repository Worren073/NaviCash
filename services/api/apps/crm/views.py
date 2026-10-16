"""views — CRM del negocio."""

from __future__ import annotations

import json
from decimal import Decimal, DecimalException

from django.db import IntegrityError, transaction
from django.db.models import F, Prefetch, Q
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.business.models import Business
from apps.core.permissions import IsOwner
from apps.crm.models import (
    BusinessContact,
    ChatConversation,
    ChatMessage,
    CollectionFollowUp,
    Invoice,
    Order,
    Product,
    ProductCategory,
    StockAdjustment,
    WhatsAppConfig,
)
from apps.crm.services import GOODS_OUT_STATUSES, requires_integer_amounts
from apps.crm.tax_id import TAX_ID_TYPES, tax_id_search_term
from apps.crm.whatsapp_service import (
    WhatsAppSendError,
    describe_inbound,
    extract_changes,
    send_text,
    verify_signature,
)
from apps.crm.serializers import (
    BusinessContactSerializer,
    ChatConversationSerializer,
    ChatMessageSerializer,
    CollectionFollowUpSerializer,
    InvoiceReadSerializer,
    InvoiceWriteSerializer,
    OrderReadSerializer,
    OrderWriteSerializer,
    ProductCategorySerializer,
    ProductSerializer,
    WhatsAppConfigSerializer,
)


class BusinessContactViewSet(viewsets.ModelViewSet):
    """CRUD de clientes y proveedores del negocio."""

    serializer_class = BusinessContactSerializer
    permission_classes = [IsOwner]

    def get_queryset(self):
        """Contactos del usuario autenticado, con búsqueda y filtros opcionales."""
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
        doc_type = self.request.query_params.get("tax_id_type")
        if doc_type:
            # Filtra SOLO por tipo de cédula (V/J/E). Va aparte de ``search``
            # porque un prefijo suelto ("V-") no sirve: al normalizarlo queda
            # vacío y ``icontains ""`` empareja con todos los contactos.
            prefix = doc_type.strip().upper()
            if prefix not in TAX_ID_TYPES:
                raise ValidationError(
                    {
                        "tax_id_type": (
                            f"Tipo de cédula inválido. Opciones: "
                            f"{', '.join(TAX_ID_TYPES)}."
                        )
                    }
                )
            qs = qs.filter(tax_id__istartswith=f"{prefix}-")
        return qs.order_by("-created_at")

    def perform_destroy(self, instance: BusinessContact) -> None:
        """Bloquea borrar contactos con facturas o pedidos asociados.

        ``Invoice.contact`` y ``Order.contact`` son ``PROTECT``: sin esta guarda
        el ``ProtectedError`` del motor escaparía como un 500. Aquí se traduce a
        un 400 legible antes de tocar la base de datos.
        """
        if instance.invoices.exists() or instance.orders.exists():
            raise ValidationError(
                "No se puede eliminar un contacto con facturas o pedidos "
                "asociados. Edita esos documentos para reasignar el contacto "
                "primero."
            )
        instance.delete()


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
        return qs.order_by("-issue_date", "-created_at")

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


class OrderViewSet(viewsets.ModelViewSet):
    """Pedidos de compra a proveedores del negocio."""

    permission_classes = [IsOwner]
    filterset_fields = ["status"]

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return OrderWriteSerializer
        return OrderReadSerializer

    def get_queryset(self):
        """Pedidos del usuario, con búsqueda y filtros opcionales."""
        qs = (
            Order.objects.filter(user=self.request.user)
            .select_related("business", "contact")
            .prefetch_related("items", "payments")
        )
        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(
                Q(number__icontains=search) | Q(contact__name__icontains=search)
            )
        order_status = self.request.query_params.get("status")
        if order_status:
            qs = qs.filter(status=order_status)
        return qs.order_by("-order_date", "-created_at")

    def _read_response(self, instance, status_code: int = 200):
        """Serializa con el serializer de lectura (más campos computados)."""
        serializer = OrderReadSerializer(
            instance, context=self.get_serializer_context()
        )
        return Response(serializer.data, status=status_code)

    def _fresh_order(self, order: Order) -> Order:
        """Recarga el pedido tras una acción para no leer caches viejas."""
        return (
            Order.objects.select_related("business", "contact")
            .prefetch_related("items", "payments")
            .get(pk=order.pk)
        )

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

    def perform_destroy(self, instance: Order):
        """Impide borrar pedidos con pagos o que ya salieron de borrador."""
        if instance.payments.exists():
            raise ValidationError("No se puede borrar un pedido con pagos registrados.")
        if instance.status != "borrador":
            raise ValidationError("Solo se pueden borrar pedidos en borrador.")
        instance.delete()

    @action(detail=True, methods=["post"])
    def send(self, request, pk=None):
        """Marca un pedido en borrador como «en camino»."""
        order = self.get_object()
        from apps.crm.services import send_order

        send_order(order)
        return Response(self.get_serializer(self._fresh_order(order)).data)

    @action(detail=True, methods=["post"])
    def pay(self, request, pk=None):
        """Registra un pago al proveedor; crea la salida en la billetera."""
        order = self.get_object()
        from apps.crm.services import record_order_payment

        amount = request.data.get("amount")
        if not amount:
            return Response(
                {"detail": "Debes indicar el monto del pago.", "code": "validation_error"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        record_order_payment(
            order,
            Decimal(str(amount)),
            note=request.data.get("note", ""),
        )
        return Response(self.get_serializer(self._fresh_order(order)).data)

    @action(detail=True, methods=["post"])
    def receive(self, request, pk=None):
        """Marca el pedido como recibido e integra la mercancía al inventario."""
        order = self.get_object()
        from apps.crm.services import receive_order

        receive_order(order)
        return Response(self.get_serializer(self._fresh_order(order)).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        """Anula el pedido (congela el documento, no revierte pagos)."""
        order = self.get_object()
        from apps.crm.services import cancel_order

        cancel_order(order)
        return Response(self.get_serializer(self._fresh_order(order)).data)


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
        return qs.order_by("-created_at")

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


# ---------------------------------------------------------------------------
# Mensajería de redes sociales (WhatsApp Cloud API)
# ---------------------------------------------------------------------------


def _match_contact(business: Business, external_id: str) -> BusinessContact | None:
    """Intenta vincular un número entrante con un contacto del directorio.

    Compara por los últimos dígitos (tolerando prefijos y separadores); si no
    hay coincidencia, la conversación queda sin contacto (se puede vincular
    manualmente más adelante).
    """
    digits = "".join(ch for ch in external_id if ch.isdigit())
    if len(digits) < 7:
        return None
    suffix = digits[-9:] if len(digits) >= 9 else digits
    candidates = BusinessContact.objects.filter(business=business).exclude(phone="")
    for contact in candidates:
        contact_digits = "".join(ch for ch in contact.phone if ch.isdigit())
        if contact_digits and contact_digits.endswith(suffix):
            return contact
    return None


def _ingest_inbound_message(config: WhatsAppConfig, raw: dict, name_by_wa: dict) -> None:
    """Guarda un mensaje entrante y actualiza el resumen de su conversación."""
    info = describe_inbound(raw)
    sender = info["from"]
    if not sender:
        return
    external_id = info["external_id"]
    # Deduplicación: Meta reentrega el webhook hasta confirmar el 200.
    if external_id and ChatMessage.objects.filter(external_id=external_id).exists():
        return

    with transaction.atomic():
        conversation, _ = ChatConversation.objects.get_or_create(
            user=config.user,
            platform="whatsapp",
            external_id=sender,
            defaults={
                "business": config.business,
                "contact_name": name_by_wa.get(sender, ""),
                "contact": _match_contact(config.business, sender),
            },
        )
        ChatMessage.objects.create(
            user=config.user,
            conversation=conversation,
            external_id=external_id,
            direction="in",
            message_type=info["type"],
            body=info["body"],
            status="received",
        )
        conversation.last_message_at = timezone.now()
        conversation.last_message_preview = info["body"][:200]
        conversation.unread_count = F("unread_count") + 1
        if not conversation.contact_name and name_by_wa.get(sender):
            conversation.contact_name = name_by_wa[sender][:120]
        conversation.save(
            update_fields=[
                "last_message_at",
                "last_message_preview",
                "unread_count",
                "contact_name",
                "updated_at",
            ]
        )


def _apply_status_update(config: WhatsAppConfig, status_row: dict) -> None:
    """Actualiza el estado de entrega/lectura de un mensaje saliente."""
    wamid = status_row.get("id")
    new_status = status_row.get("status")
    if not wamid or new_status not in {"sent", "delivered", "read", "failed"}:
        return
    ChatMessage.objects.filter(
        user=config.user, external_id=wamid, direction="out"
    ).update(status=new_status)


def _process_change(config: WhatsAppConfig, value: dict) -> None:
    """Procesa un bloque ``value`` del webhook: mensajes y estados."""
    contacts = value.get("contacts") or []
    name_by_wa = {
        c.get("wa_id"): (c.get("profile") or {}).get("name", "")
        for c in contacts
        if c.get("wa_id")
    }
    for raw in value.get("messages") or []:
        _ingest_inbound_message(config, raw, name_by_wa)
    for status_row in value.get("statuses") or []:
        _apply_status_update(config, status_row)


class WhatsAppWebhookView(APIView):
    """Webhook público de la WhatsApp Cloud API (sin JWT).

    - ``GET``: handshake de verificación de Meta (``hub.challenge``).
    - ``POST``: entrega de eventos; se autentica con la firma HMAC
      ``X-Hub-Signature-256`` usando el ``app_secret`` del negocio dueño del
      número. Throttle desactivado (lo llama Meta, no un usuario).
    """

    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes: list = []

    def get(self, request):
        mode = request.query_params.get("hub.mode")
        token = request.query_params.get("hub.verify_token")
        challenge = request.query_params.get("hub.challenge", "")
        if (
            mode == "subscribe"
            and token
            and WhatsAppConfig.objects.filter(verify_token=token, is_active=True).exists()
        ):
            return HttpResponse(challenge, content_type="text/plain")
        return HttpResponse("Forbidden", status=403, content_type="text/plain")

    def post(self, request):
        raw_body = request.body or b""
        try:
            payload = json.loads(raw_body or b"{}")
        except (ValueError, TypeError):
            return Response(
                {"detail": "Payload inválido.", "code": "validation_error"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        changes = extract_changes(payload)
        config_by_number: dict[str, WhatsAppConfig] = {}
        for change in changes:
            number = change["phone_number_id"]
            if not number:
                continue
            config = (
                WhatsAppConfig.objects.filter(phone_number_id=number, is_active=True)
                .select_related("user", "business")
                .first()
            )
            if config is None:
                continue
            config_by_number[number] = config

        if config_by_number:
            # La firma es la única autenticación del webhook: se valida con el
            # app_secret del número antes de procesar (AUDIT: sin firma no se
            # ingiere nada). Se compara en tiempo constante.
            signature = request.headers.get("X-Hub-Signature-256", "")
            for config in config_by_number.values():
                if not verify_signature(config.app_secret, raw_body, signature):
                    return Response(
                        {"detail": "Firma inválida."},
                        status=status.HTTP_403_FORBIDDEN,
                    )
            for change in changes:
                config = config_by_number.get(change["phone_number_id"])
                if config is not None:
                    _process_change(config, change["value"])

        # Siempre 200 para que Meta no reintente (eventos desconocidos incluidos).
        return Response({"status": "ok"})


class WhatsAppConfigView(APIView):
    """Credenciales de WhatsApp del negocio autenticado (una por usuario)."""

    permission_classes = [IsAuthenticated]

    def _business(self, request) -> Business | None:
        return Business.objects.filter(user=request.user).first()

    def get(self, request):
        config = WhatsAppConfig.objects.filter(user=request.user).first()
        if config is None:
            return Response({"connected": False})
        data = WhatsAppConfigSerializer(config).data
        data["connected"] = config.is_active
        return Response(data)

    def _save(self, request):
        business = self._business(request)
        if business is None:
            return Response(
                {"detail": "Crea tu negocio antes de conectar WhatsApp.", "code": "validation_error"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        config = WhatsAppConfig.objects.filter(user=request.user).first()
        serializer = WhatsAppConfigSerializer(
            config, data=request.data, partial=config is not None
        )
        serializer.is_valid(raise_exception=True)
        try:
            serializer.save(user=request.user, business=business)
        except IntegrityError:
            return Response(
                {
                    "detail": "Ese número de WhatsApp ya está conectado a otra cuenta.",
                    "code": "validation_error",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        data = WhatsAppConfigSerializer(serializer.instance).data
        data["connected"] = serializer.instance.is_active
        return Response(data, status=status.HTTP_200_OK)

    def post(self, request):
        return self._save(request)

    def put(self, request):
        return self._save(request)

    def delete(self, request):
        deleted, _ = WhatsAppConfig.objects.filter(user=request.user).delete()
        if not deleted:
            return Response(
                {"detail": "No hay una conexión de WhatsApp configurada."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class ChatConversationViewSet(viewsets.ReadOnlyModelViewSet):
    """Inbox unificado del negocio: hilos, mensajes y respuesta manual."""

    serializer_class = ChatConversationSerializer
    permission_classes = [IsOwner]

    def get_queryset(self):
        qs = ChatConversation.objects.filter(user=self.request.user).select_related("contact")
        platform = self.request.query_params.get("platform")
        if platform:
            qs = qs.filter(platform=platform)
        return qs.order_by("-last_message_at", "-created_at")

    def get_throttles(self):
        """Limita solo el envío saliente (respuesta manual) a la API de Meta."""
        self.throttle_scope = "chat_send" if self.action == "send" else ""
        return super().get_throttles()

    @action(detail=True, methods=["get"])
    def messages(self, request, pk=None):
        """Devuelve los mensajes del hilo y marca la conversación como leída."""
        conversation = self.get_object()
        qs = conversation.messages.all()
        page = self.paginate_queryset(qs)
        serializer = ChatMessageSerializer(page if page is not None else qs, many=True)
        if conversation.unread_count:
            conversation.unread_count = 0
            conversation.save(update_fields=["unread_count", "updated_at"])
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def send(self, request, pk=None):
        """Envía una respuesta de texto al cliente por WhatsApp."""
        conversation = self.get_object()
        text = str(request.data.get("text") or "").strip()
        if not text:
            return Response(
                {"detail": "Escribe un mensaje.", "code": "validation_error"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(text) > 4096:
            return Response(
                {"detail": "El mensaje es demasiado largo (máx. 4096 caracteres).", "code": "validation_error"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        config = WhatsAppConfig.objects.filter(
            user=request.user, is_active=True
        ).first()
        if config is None:
            return Response(
                {
                    "detail": "Conecta tu WhatsApp antes de responder.",
                    "code": "whatsapp_not_connected",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            wamid = send_text(
                config.phone_number_id,
                config.access_token,
                conversation.external_id,
                text,
            )
        except WhatsAppSendError as exc:
            return Response(
                {"detail": exc.message, "code": exc.code},
                status=status.HTTP_400_BAD_REQUEST,
            )

        message = ChatMessage.objects.create(
            user=request.user,
            conversation=conversation,
            external_id=wamid,
            direction="out",
            message_type="text",
            body=text,
            status="sent",
        )
        conversation.last_message_at = timezone.now()
        conversation.last_message_preview = text[:200]
        conversation.save(update_fields=["last_message_at", "last_message_preview", "updated_at"])
        return Response(ChatMessageSerializer(message).data, status=status.HTTP_201_CREATED)
