"""models — CRM ligero para pequeños negocios.

Fase 1: Directorio de clientes y proveedores del negocio (`BusinessContact`).
Fase 2: Facturación y cuentas por cobrar (`Invoice`, `InvoiceItem`, `InvoicePayment`).
Fase 3: Pipeline de cobranza (`CollectionFollowUp`).
Fase 4: Inventario conectado a facturación (`Product`, `ProductCategory`, `StockAdjustment`).
"""

from __future__ import annotations

import secrets

from django.db import models
from django.db.models.functions import Lower

from apps.business.models import Business
from apps.core.currency import CURRENCY_CHOICES, MONEY_DECIMALS
from apps.core.crypto import decrypt_value, encrypt_value
from apps.core.models import OwnedModel
from apps.transactions.models import Transaction


class BusinessContact(OwnedModel):
    """Cliente o proveedor vinculado a un negocio.

    Es independiente del modelo ``Contact`` de operaciones personales.
    """

    CONTACT_TYPES = [
        ("cliente", "Cliente"),
        ("proveedor", "Proveedor"),
        ("ambos", "Ambos"),
    ]

    CUSTOMER_TYPES = [
        ("minorista", "Minorista"),
        ("mayorista", "Mayorista"),
    ]

    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="contacts",
        verbose_name="Negocio",
    )
    name = models.CharField(max_length=120, verbose_name="Nombre")
    email = models.EmailField(blank=True, default="", verbose_name="Correo")
    phone = models.CharField(max_length=40, blank=True, default="", verbose_name="Teléfono")
    address = models.CharField(max_length=255, blank=True, default="", verbose_name="Dirección")
    tax_id = models.CharField(
        max_length=30, blank=True, default="", verbose_name="RIF/NIT"
    )
    type = models.CharField(
        max_length=10,
        choices=CONTACT_TYPES,
        default="cliente",
        verbose_name="Tipo",
    )
    customer_type = models.CharField(
        max_length=10,
        choices=CUSTOMER_TYPES,
        blank=True,
        default="",
        verbose_name="Tipo de cliente",
    )
    payment_terms_days = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="Días de crédito",
    )
    credit_limit = models.DecimalField(
        max_digits=20,
        decimal_places=MONEY_DECIMALS,
        null=True,
        blank=True,
        verbose_name="Límite de crédito",
    )
    currency = models.CharField(
        max_length=3,
        choices=CURRENCY_CHOICES,
        default="USD",
        verbose_name="Moneda del límite",
    )
    notes = models.TextField(blank=True, default="", verbose_name="Notas")
    is_active = models.BooleanField(default=True, verbose_name="Activo")

    class Meta:
        verbose_name = "Contacto de negocio"
        verbose_name_plural = "Contactos de negocio"
        ordering = ["name"]
        indexes = [
            models.Index(fields=["user", "business", "name"], name="crm_contact_ub_name_idx"),
            models.Index(fields=["user", "business", "type"], name="crm_contact_ub_type_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["business", "tax_id"],
                name="uniq_business_contact_tax_id",
                # Permite múltiples contactos sin RIF (tax_id vacío).
                condition=models.Q(tax_id__gt=""),
            ),
        ]

    def __str__(self) -> str:
        return self.name


INVOICE_STATUSES = [
    ("borrador", "Borrador"),
    ("enviada", "Enviada"),
    ("parcial", "Parcial"),
    ("pagada", "Pagada"),
    ("vencida", "Vencida"),
    ("anulada", "Anulada"),
]


class Invoice(OwnedModel):
    """Factura de venta a crédito o de contado del negocio."""

    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="invoices",
        verbose_name="Negocio",
    )
    contact = models.ForeignKey(
        BusinessContact,
        on_delete=models.PROTECT,
        related_name="invoices",
        verbose_name="Contacto",
    )
    number = models.CharField(max_length=20, verbose_name="Número")
    issue_date = models.DateField(verbose_name="Fecha de emisión")
    issued_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Emitida el",
        help_text="Fecha y hora reales de emisión (las del dispositivo que la creó).",
    )
    due_date = models.DateField(verbose_name="Fecha de vencimiento")
    status = models.CharField(
        max_length=10,
        choices=INVOICE_STATUSES,
        default="borrador",
        verbose_name="Estado",
    )
    subtotal = models.DecimalField(
        max_digits=20, decimal_places=MONEY_DECIMALS, verbose_name="Subtotal"
    )
    tax_amount = models.DecimalField(
        max_digits=20,
        decimal_places=MONEY_DECIMALS,
        default=0,
        verbose_name="Impuesto",
    )
    total = models.DecimalField(
        max_digits=20, decimal_places=MONEY_DECIMALS, verbose_name="Total"
    )
    amount_paid = models.DecimalField(
        max_digits=20,
        decimal_places=MONEY_DECIMALS,
        default=0,
        verbose_name="Monto pagado",
    )
    balance_due = models.DecimalField(
        max_digits=20,
        decimal_places=MONEY_DECIMALS,
        verbose_name="Saldo pendiente",
    )
    currency = models.CharField(
        max_length=3,
        choices=CURRENCY_CHOICES,
        default="USD",
        verbose_name="Moneda",
    )
    notes = models.TextField(blank=True, default="", verbose_name="Notas")

    class Meta:
        verbose_name = "Factura"
        verbose_name_plural = "Facturas"
        ordering = ["-issue_date", "-created_at"]
        indexes = [
            models.Index(
                fields=["user", "business", "status"],
                name="crm_inv_ub_status_idx",
            ),
            models.Index(
                fields=["user", "business", "due_date"],
                name="crm_inv_ub_due_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["business", "number"],
                name="uniq_business_invoice_number",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.number} - {self.contact.name}"


class InvoiceItem(OwnedModel):
    """Línea de factura."""

    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name="Factura",
    )
    product = models.ForeignKey(
        "Product",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoice_items",
        verbose_name="Producto del catálogo",
    )
    description = models.CharField(max_length=160, verbose_name="Descripción")
    quantity = models.DecimalField(
        max_digits=10, decimal_places=2, verbose_name="Cantidad"
    )
    unit_price = models.DecimalField(
        max_digits=20, decimal_places=MONEY_DECIMALS, verbose_name="Precio unitario"
    )
    cost_price = models.DecimalField(
        max_digits=20,
        decimal_places=MONEY_DECIMALS,
        null=True,
        blank=True,
        verbose_name="Costo de compra",
        help_text="Costo del producto congelado al emitir la factura.",
    )
    discount = models.DecimalField(
        max_digits=20,
        decimal_places=MONEY_DECIMALS,
        default=0,
        verbose_name="Descuento",
    )
    total = models.DecimalField(
        max_digits=20, decimal_places=MONEY_DECIMALS, verbose_name="Total"
    )

    class Meta:
        verbose_name = "Línea de factura"
        verbose_name_plural = "Líneas de factura"
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.description} ({self.quantity} x {self.unit_price})"


class InvoicePayment(OwnedModel):
    """Pago recibido contra una factura."""

    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name="payments",
        verbose_name="Factura",
    )
    transaction = models.ForeignKey(
        Transaction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoice_payments",
        verbose_name="Operación de cobro",
    )
    amount = models.DecimalField(
        max_digits=20, decimal_places=MONEY_DECIMALS, verbose_name="Monto"
    )
    paid_at = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de pago")
    note = models.CharField(max_length=200, blank=True, default="", verbose_name="Nota")

    class Meta:
        verbose_name = "Pago de factura"
        verbose_name_plural = "Pagos de facturas"
        ordering = ["-paid_at"]

    def __str__(self) -> str:
        return f"Pago {self.amount} {self.invoice.currency}"


ORDER_STATUSES = [
    ("borrador", "Borrador"),
    ("en_camino", "En camino"),
    ("recibido", "Recibido"),
    ("anulado", "Anulado"),
]


class Order(OwnedModel):
    """Pedido de compra del negocio a un proveedor.

    Al recibirse (``recibido``) las mercancías se integran de una vez al
    inventario: las líneas con producto existente solo incrementan existencias
    y las líneas con producto nuevo crean el producto del catálogo (ver
    ``apps.crm.services.receive_order``).
    """

    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="orders",
        verbose_name="Negocio",
    )
    contact = models.ForeignKey(
        BusinessContact,
        on_delete=models.PROTECT,
        related_name="orders",
        verbose_name="Proveedor",
    )
    number = models.CharField(max_length=20, verbose_name="Número")
    order_date = models.DateField(verbose_name="Fecha del pedido")
    ordered_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Registrado el",
        help_text="Fecha y hora reales del pedido (las del dispositivo que lo creó).",
    )
    due_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Fecha de vencimiento",
        help_text="Fecha prevista de pago; en falta, la calcula el contacto (días de crédito).",
    )
    received_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Recibido el",
    )
    status = models.CharField(
        max_length=10,
        choices=ORDER_STATUSES,
        default="borrador",
        verbose_name="Estado",
    )
    subtotal = models.DecimalField(
        max_digits=20, decimal_places=MONEY_DECIMALS, verbose_name="Subtotal"
    )
    shipping_amount = models.DecimalField(
        max_digits=20,
        decimal_places=MONEY_DECIMALS,
        default=0,
        verbose_name="Envío",
    )
    total = models.DecimalField(
        max_digits=20, decimal_places=MONEY_DECIMALS, verbose_name="Total"
    )
    amount_paid = models.DecimalField(
        max_digits=20,
        decimal_places=MONEY_DECIMALS,
        default=0,
        verbose_name="Monto pagado",
    )
    balance_due = models.DecimalField(
        max_digits=20,
        decimal_places=MONEY_DECIMALS,
        verbose_name="Saldo pendiente",
    )
    currency = models.CharField(
        max_length=3,
        choices=CURRENCY_CHOICES,
        default="USD",
        verbose_name="Moneda",
    )
    notes = models.TextField(blank=True, default="", verbose_name="Notas")

    class Meta:
        verbose_name = "Pedido"
        verbose_name_plural = "Pedidos"
        ordering = ["-order_date"]
        indexes = [
            models.Index(
                fields=["user", "business", "status"],
                name="crm_order_ub_status_idx",
            ),
            models.Index(
                fields=["user", "business", "order_date"],
                name="crm_order_ub_date_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["business", "number"],
                name="uniq_business_order_number",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.number} - {self.contact.name}"


class OrderItem(OwnedModel):
    """Línea de un pedido: producto del inventario o producto nuevo."""

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name="Pedido",
    )
    product = models.ForeignKey(
        "Product",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_items",
        verbose_name="Producto del catálogo",
    )
    new_product = models.JSONField(
        default=dict, blank=True, verbose_name="Datos del producto nuevo"
    )
    description = models.CharField(max_length=160, verbose_name="Descripción")
    quantity = models.DecimalField(
        max_digits=10, decimal_places=2, verbose_name="Cantidad"
    )
    unit_price = models.DecimalField(
        max_digits=20, decimal_places=MONEY_DECIMALS, verbose_name="Precio unitario"
    )
    cost_price = models.DecimalField(
        max_digits=20,
        decimal_places=MONEY_DECIMALS,
        null=True,
        blank=True,
        verbose_name="Costo de compra",
        help_text="Costo del producto congelado al crear el pedido.",
    )
    discount = models.DecimalField(
        max_digits=20,
        decimal_places=MONEY_DECIMALS,
        default=0,
        verbose_name="Descuento",
    )
    total = models.DecimalField(
        max_digits=20, decimal_places=MONEY_DECIMALS, verbose_name="Total"
    )

    class Meta:
        verbose_name = "Línea de pedido"
        verbose_name_plural = "Líneas de pedido"
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.description} ({self.quantity} x {self.unit_price})"


class OrderPayment(OwnedModel):
    """Pago realizado contra un pedido."""

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="payments",
        verbose_name="Pedido",
    )
    transaction = models.ForeignKey(
        Transaction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_payments",
        verbose_name="Operación de pago",
    )
    amount = models.DecimalField(
        max_digits=20, decimal_places=MONEY_DECIMALS, verbose_name="Monto"
    )
    paid_at = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de pago")
    note = models.CharField(max_length=200, blank=True, default="", verbose_name="Nota")

    class Meta:
        verbose_name = "Pago de pedido"
        verbose_name_plural = "Pagos de pedidos"
        ordering = ["-paid_at"]

    def __str__(self) -> str:
        return f"Pago {self.amount} {self.order.currency}"


FOLLOW_UP_CHANNELS = [
    ("llamada", "Llamada"),
    ("email", "Correo"),
    ("whatsapp", "WhatsApp"),
    ("visita", "Visita"),
    ("otro", "Otro"),
]

FOLLOW_UP_OUTCOMES = [
    ("sin_respuesta", "Sin respuesta"),
    ("promesa_pago", "Promesa de pago"),
    ("pago_realizado", "Pago realizado"),
    ("rechazado", "Rechazado"),
    ("otro", "Otro"),
]


class CollectionFollowUp(OwnedModel):
    """Seguimiento de cobranza registrado contra una factura abierta.

    Modela la gestión manual de cobro: canal de contacto, resultado de la
    gestión y, si hay promesa de pago, la fecha comprometida.
    """

    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name="follow_ups",
        verbose_name="Factura",
    )
    channel = models.CharField(
        max_length=10,
        choices=FOLLOW_UP_CHANNELS,
        verbose_name="Canal",
    )
    outcome = models.CharField(
        max_length=16,
        choices=FOLLOW_UP_OUTCOMES,
        verbose_name="Resultado",
    )
    promised_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Fecha de pago prometida",
    )
    notes = models.TextField(blank=True, default="", verbose_name="Notas")

    class Meta:
        verbose_name = "Seguimiento de cobranza"
        verbose_name_plural = "Seguimientos de cobranza"
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["user", "invoice", "created_at"],
                name="crm_followup_ui_created",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.invoice.number} - {self.outcome}"


class ProductCategory(OwnedModel):
    """Categoría para agrupar productos del inventario."""

    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="product_categories",
        verbose_name="Negocio",
    )
    name = models.CharField(max_length=60, verbose_name="Nombre")

    class Meta:
        verbose_name = "Categoría de producto"
        verbose_name_plural = "Categorías de producto"
        ordering = ["name"]
        indexes = [
            models.Index(
                fields=["user", "business", "name"],
                name="crm_prod_cat_ub_name_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                Lower("name"),
                "business",
                name="uniq_business_product_category_name",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class Product(OwnedModel):
    """Producto del inventario del negocio.

    ``stock_quantity`` se descuenta al crear/envíar facturas y se repone al
    anularlas (ver ``apps.crm.services``). Los precios de venta son dos: el
    general (``unit_price``) y el mayorista (``wholesale_price``), que se elige
    según el ``customer_type`` del cliente al armar la factura.
    """

    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="products",
        verbose_name="Negocio",
    )
    name = models.CharField(max_length=120, verbose_name="Nombre")
    sku = models.CharField(
        max_length=40, blank=True, default="", verbose_name="Código/SKU"
    )
    description = models.TextField(blank=True, default="", verbose_name="Descripción")
    unit = models.CharField(
        max_length=12,
        choices=[("unidad", "Unidad"), ("kg", "Kg")],
        blank=True,
        default="unidad",
        verbose_name="Unidad de medida",
    )
    unit_price = models.DecimalField(
        max_digits=20,
        decimal_places=MONEY_DECIMALS,
        verbose_name="Precio de venta",
    )
    wholesale_price = models.DecimalField(
        max_digits=20,
        decimal_places=MONEY_DECIMALS,
        null=True,
        blank=True,
        verbose_name="Precio mayorista",
    )
    cost_price = models.DecimalField(
        max_digits=20,
        decimal_places=MONEY_DECIMALS,
        null=True,
        blank=True,
        verbose_name="Costo de compra",
    )
    category = models.ForeignKey(
        ProductCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
        verbose_name="Categoría",
    )
    supplier = models.ForeignKey(
        BusinessContact,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
        verbose_name="Proveedor",
    )
    stock_quantity = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name="Existencias",
    )
    low_stock_threshold = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Alerta de stock mínimo",
    )
    is_active = models.BooleanField(default=True, verbose_name="Activo")

    class Meta:
        verbose_name = "Producto"
        verbose_name_plural = "Productos"
        ordering = ["name"]
        indexes = [
            models.Index(fields=["user", "business", "name"], name="crm_prod_ub_name_idx"),
            models.Index(fields=["user", "business", "sku"], name="crm_prod_ub_sku_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                Lower("name"),
                "business",
                name="uniq_business_product_name",
            ),
            models.UniqueConstraint(
                fields=["business", "sku"],
                condition=models.Q(sku__gt=""),
                name="uniq_business_product_sku",
            ),
            models.CheckConstraint(
                condition=models.Q(stock_quantity__gte=0),
                name="ck_product_stock_nonneg",
            ),
            models.CheckConstraint(
                condition=models.Q(unit_price__gte=0),
                name="ck_product_unit_price_nonneg",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.stock_quantity} {self.unit})"


class StockAdjustment(OwnedModel):
    """Auditoría de cada movimiento de existencias (venta, anulación o ajuste)."""

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="adjustments",
        verbose_name="Producto",
    )
    delta = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Variación de existencias",
    )
    reason = models.CharField(max_length=200, blank=True, default="", verbose_name="Motivo")

    class Meta:
        verbose_name = "Ajuste de inventario"
        verbose_name_plural = "Ajustes de inventario"
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["user", "product", "created_at"],
                name="crm_stkadj_up_created_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.product.name} {self.delta:+}"


# ---------------------------------------------------------------------------
# Mensajería de redes sociales (WhatsApp Cloud API) — Fase 1: inbox + respuesta
# ---------------------------------------------------------------------------


def generate_verify_token() -> str:
    """Token de verificación de webhook, aleatorio y difícil de adivinar."""
    return secrets.token_urlsafe(32)


class WhatsAppConfig(OwnedModel):
    """Credenciales del negocio para la WhatsApp Cloud API de Meta.

    Cada negocio conecta su propio número (multi-inquilino): los datos salen de
    su propia app de Meta. Los secretos (``access_token`` y ``app_secret``) se
    guardan CIFRADOS con Fernet y nunca se devuelven al cliente.

    ``verify_token`` es un secreto compartido que Meta reenvía en el handshake
    del webhook; permite localizar al negocio cuando llega el GET de
    verificación (el POST se enruta por ``phone_number_id``).
    """

    business = models.OneToOneField(
        Business,
        on_delete=models.CASCADE,
        related_name="whatsapp_config",
        verbose_name="Negocio",
    )
    phone_number_id = models.CharField(
        max_length=64, unique=True, verbose_name="ID del número (phone_number_id)"
    )
    waba_id = models.CharField(
        max_length=64, blank=True, default="", verbose_name="ID de la cuenta (WABA)"
    )
    display_phone_number = models.CharField(
        max_length=40, blank=True, default="", verbose_name="Número visible"
    )
    access_token_encrypted = models.TextField(
        blank=True, default="", verbose_name="Token de acceso (cifrado)"
    )
    app_secret_encrypted = models.TextField(
        blank=True, default="", verbose_name="App Secret (cifrado)"
    )
    verify_token = models.CharField(
        max_length=64,
        unique=True,
        default=generate_verify_token,
        verbose_name="Token de verificación del webhook",
    )
    is_active = models.BooleanField(default=True, verbose_name="Activo")

    class Meta:
        verbose_name = "Configuración de WhatsApp"
        verbose_name_plural = "Configuraciones de WhatsApp"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"WhatsApp {self.display_phone_number or self.phone_number_id}"

    @property
    def access_token(self) -> str:
        """Token de acceso en claro (para llamar a la API de Meta)."""
        return decrypt_value(self.access_token_encrypted)

    @access_token.setter
    def access_token(self, raw: str) -> None:
        self.access_token_encrypted = encrypt_value(raw)

    @property
    def app_secret(self) -> str:
        """App Secret en claro (para verificar la firma del webhook)."""
        return decrypt_value(self.app_secret_encrypted)

    @app_secret.setter
    def app_secret(self, raw: str) -> None:
        self.app_secret_encrypted = encrypt_value(raw)


CHAT_PLATFORMS = [
    ("whatsapp", "WhatsApp"),
]

CONVERSATION_STATUSES = [
    ("abierta", "Abierta"),
    ("archivada", "Archivada"),
]


class ChatConversation(OwnedModel):
    """Hilo de conversación con un cliente en una plataforma social."""

    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="chat_conversations",
        verbose_name="Negocio",
    )
    contact = models.ForeignKey(
        BusinessContact,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chat_conversations",
        verbose_name="Contacto",
    )
    platform = models.CharField(
        max_length=20, choices=CHAT_PLATFORMS, default="whatsapp", verbose_name="Plataforma"
    )
    external_id = models.CharField(
        max_length=64,
        verbose_name="ID externo",
        help_text="Identificador del interlocutor en la plataforma (wa_id/teléfono).",
    )
    contact_name = models.CharField(
        max_length=120, blank=True, default="", verbose_name="Nombre mostrado"
    )
    last_message_at = models.DateTimeField(
        null=True, blank=True, db_index=True, verbose_name="Último mensaje"
    )
    last_message_preview = models.CharField(
        max_length=200, blank=True, default="", verbose_name="Vista previa"
    )
    unread_count = models.PositiveIntegerField(default=0, verbose_name="No leídos")
    status = models.CharField(
        max_length=20,
        choices=CONVERSATION_STATUSES,
        default="abierta",
        verbose_name="Estado",
    )

    class Meta:
        verbose_name = "Conversación"
        verbose_name_plural = "Conversaciones"
        ordering = ["-last_message_at", "-created_at"]
        indexes = [
            models.Index(
                fields=["user", "platform", "last_message_at"],
                name="crm_chat_user_plat_last_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "platform", "external_id"],
                name="uniq_user_platform_conversation",
            ),
        ]

    def __str__(self) -> str:
        return self.contact_name or self.external_id


MESSAGE_DIRECTIONS = [
    ("in", "Entrante"),
    ("out", "Saliente"),
]

MESSAGE_STATUSES = [
    ("received", "Recibido"),
    ("sent", "Enviado"),
    ("delivered", "Entregado"),
    ("read", "Leído"),
    ("failed", "Fallido"),
]


class ChatMessage(OwnedModel):
    """Mensaje individual dentro de una conversación.

    ``external_id`` es el ``wamid`` de Meta: único para deduplicar
    reentregas del webhook (entrega "at-least-once").
    """

    conversation = models.ForeignKey(
        ChatConversation,
        on_delete=models.CASCADE,
        related_name="messages",
        verbose_name="Conversación",
    )
    external_id = models.CharField(
        max_length=128, blank=True, default="", verbose_name="ID externo"
    )
    direction = models.CharField(
        max_length=3, choices=MESSAGE_DIRECTIONS, verbose_name="Dirección"
    )
    message_type = models.CharField(
        max_length=16, default="text", verbose_name="Tipo"
    )
    body = models.TextField(blank=True, default="", verbose_name="Contenido")
    status = models.CharField(
        max_length=16, choices=MESSAGE_STATUSES, default="received", verbose_name="Estado"
    )

    class Meta:
        verbose_name = "Mensaje de chat"
        verbose_name_plural = "Mensajes de chat"
        ordering = ["created_at"]
        indexes = [
            models.Index(
                fields=["conversation", "created_at"],
                name="crm_chatmsg_conv_created_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["external_id"],
                condition=models.Q(external_id__gt=""),
                name="uniq_chat_message_external_id",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.direction}: {self.body[:40]}"
