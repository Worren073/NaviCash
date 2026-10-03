"""models — CRM ligero para pequeños negocios.

Fase 1: Directorio de clientes y proveedores del negocio (`BusinessContact`).
Fase 2: Facturación y cuentas por cobrar (`Invoice`, `InvoiceItem`, `InvoicePayment`).
"""

from __future__ import annotations

from django.db import models

from apps.business.models import Business
from apps.core.currency import CURRENCY_CHOICES, MONEY_DECIMALS
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
    description = models.CharField(max_length=160, verbose_name="Descripción")
    quantity = models.DecimalField(
        max_digits=10, decimal_places=2, verbose_name="Cantidad"
    )
    unit_price = models.DecimalField(
        max_digits=20, decimal_places=MONEY_DECIMALS, verbose_name="Precio unitario"
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
