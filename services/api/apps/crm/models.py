"""models — CRM ligero para pequeños negocios.

Fase 1: Directorio de clientes y proveedores del negocio (`BusinessContact`).
"""

from __future__ import annotations

from django.db import models

from apps.business.models import Business
from apps.core.currency import CURRENCY_CHOICES, MONEY_DECIMALS
from apps.core.models import OwnedModel


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
