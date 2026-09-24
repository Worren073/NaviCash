"""models — Listas de compras del mercado (checklists).

Una lista reúne productos (ítems). Al tildar un producto se abre un modal
donde el usuario registra precio por unidad y cantidad (en la moneda de la
lista); el subtotal se calcula automáticamente y se muestra en USD y VES con
la tasa del día. Al completar la lista se elige la cuenta de pago y el total
real (editable); el egreso se registra como una operación ``tipo="pago"`` que
descuenta la cuenta de inmediato (patrón ``renew_subscription``: una sola
transacción atómica con ``mark_paid`` / ``adjust_balance``).
"""

from __future__ import annotations

from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models

from apps.core.currency import CURRENCY_CHOICES, MONEY_DECIMALS, round_money
from apps.core.models import OwnedModel

#: Estados de la lista de compras.
CHECKLIST_STATES = [
    ("en_curso", "En curso"),
    ("completada", "Completada"),
]


class ChecklistManager(models.Manager):
    """Manager por defecto: excluye listas ocultas (soft-delete, C4)."""

    def get_queryset(self):
        """Solo listas no borradas."""
        return super().get_queryset().filter(is_deleted=False)


class ShoppingList(OwnedModel):
    """Lista de compras del usuario.

    Campos:
        name: nombre visible (ej. "Mercado de la semana").
        currency: moneda en la que se registran los precios (USD/VES).
        estado: en_curso / completada (se fija al descontar el egreso).
        wallet: cuenta desde la que se pagó (se fija al completar).
        transaction: operación ``tipo="pago"`` generada al completar
            (OneToOne: una lista = una operación).
        total_real: total efectivamente pagado (se fija al completar).
    """

    name = models.CharField(max_length=120, verbose_name="Nombre")
    currency = models.CharField(
        max_length=3, choices=CURRENCY_CHOICES, default="USD", verbose_name="Moneda"
    )
    estado = models.CharField(
        max_length=12, choices=CHECKLIST_STATES, default="en_curso", verbose_name="Estado"
    )
    wallet = models.ForeignKey(
        "wallets.Wallet",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="shopping_lists",
        verbose_name="Cuenta del pago",
    )
    transaction = models.OneToOneField(
        "transactions.Transaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="shopping_list",
        verbose_name="Operación generada",
    )
    total_real = models.DecimalField(
        max_digits=20,
        decimal_places=MONEY_DECIMALS,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
        verbose_name="Total real",
    )
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="Completada el")
    is_deleted = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name="Oculta",
        help_text="Soft-delete (C4): la lista se oculta de la API pero conserva su historial.",
    )

    objects = ChecklistManager()
    all_objects = models.Manager()

    class Meta:
        verbose_name = "Lista de compras"
        verbose_name_plural = "Listas de compras"
        ordering = ["-created_at"]
        default_manager_name = "objects"
        indexes = [
            # A9: listado por usuario/estado y "mis listas" recientes.
            models.Index(fields=["user", "estado"]),
            models.Index(fields=["user", "created_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(estado__in=["en_curso", "completada"]),
                name="checklist_estado_valid",
                violation_error_message="Estado de lista inválido.",
            ),
            models.CheckConstraint(
                condition=models.Q(total_real__isnull=True) | models.Q(total_real__gt=0),
                name="checklist_total_real_gt_0",
                violation_error_message="El total real debe ser mayor a cero.",
            ),
            # Invariante: una lista completada tiene cuenta y operación de egreso.
            models.CheckConstraint(
                condition=models.Q(estado="en_curso")
                | (models.Q(wallet__isnull=False) & models.Q(transaction__isnull=False)),
                name="checklist_completada_con_pago",
                violation_error_message="Al completar la lista debes indicar la cuenta y generar la operación.",
            ),
            models.CheckConstraint(
                condition=models.Q(estado="en_curso") | models.Q(completed_at__isnull=False),
                name="checklist_completada_con_fecha",
                violation_error_message="Una lista completada requiere la fecha de cierre.",
            ),
        ]

    def __str__(self) -> str:
        """Representación: nombre."""
        return self.name

    @property
    def total_estimado(self) -> Decimal:
        """Suma de los subtotales de los productos tildados (moneda de la lista)."""
        from django.db.models import F, Sum

        total = self.items.filter(is_checked=True).aggregate(
            total=Sum(F("precio_unitario") * F("cantidad"))
        )["total"]
        return round_money(total or Decimal("0"))

    @property
    def progress_percent(self) -> Decimal:
        """Porcentaje de productos tildados (0.0–100.0)."""
        count = self.items.count()
        if count == 0:
            return Decimal("0.0")
        done = self.items.filter(is_checked=True).count()
        return Decimal(str(round(done / count * 100, 1)))

    def soft_delete(self) -> None:
        """Soft-delete (C4): oculta la lista; la operación sigue como historial."""
        self.is_deleted = True
        self.save(update_fields=["is_deleted", "updated_at"])


class ListItem(OwnedModel):
    """Producto de una lista de compras.

    Al marcarse, el usuario registra ``precio_unitario`` y ``cantidad`` (modal)
    en la moneda de la lista; el subtotal (precio × cantidad) se calcula al leer.
    """

    checklist = models.ForeignKey(
        ShoppingList, on_delete=models.CASCADE, related_name="items", verbose_name="Lista"
    )
    name = models.CharField(max_length=120, verbose_name="Producto")
    precio_unitario = models.DecimalField(
        max_digits=20,
        decimal_places=MONEY_DECIMALS,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
        verbose_name="Precio por unidad",
    )
    cantidad = models.PositiveSmallIntegerField(default=1, verbose_name="Cantidad")
    is_checked = models.BooleanField(default=False, verbose_name="Marcado")

    class Meta:
        verbose_name = "Producto"
        verbose_name_plural = "Productos"
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["checklist", "is_checked"]),
            models.Index(fields=["checklist", "created_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(precio_unitario__isnull=True) | models.Q(precio_unitario__gt=0),
                name="checklistitem_precio_unitario_gt_0",
                violation_error_message="El precio por unidad debe ser mayor a cero.",
            ),
            models.CheckConstraint(
                condition=models.Q(cantidad__gte=1),
                name="checklistitem_cantidad_gte_1",
                violation_error_message="La cantidad debe ser al menos 1.",
            ),
        ]

    def __str__(self) -> str:
        """Representación: nombre."""
        return self.name

    @property
    def subtotal(self) -> Decimal:
        """Precio por unidad × cantidad (0 si aún no hay precio registrado)."""
        if self.precio_unitario is None:
            return Decimal("0.00")
        return round_money(self.precio_unitario * self.cantidad)