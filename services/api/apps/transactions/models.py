"""models — Modelos de operaciones: Transaction, Category y Contact.

Convenciones:
- ``moneda``: moneda original de la operación.
- ``monto``: cantidad en la moneda original (Decimal, nunca float).
- ``monto_usd`` / ``tasa_usd`` / ``fuente_tasa``: conversión CONGELADA en el
  momento de registrar (R2/R4). Se usa para reportes consistentes.
- El estado "retrasado" NO se persiste: se calcula al consultar
  (``is_overdue``) para no depender de un cron para estar al día (R8).
"""

from __future__ import annotations

from datetime import date

from django.db import models
from django.utils import timezone

from apps.core.currency import CURRENCY_CHOICES, MONEY_DECIMALS
from apps.core.models import OwnedModel


class TransactionManager(models.Manager):
    """Manager por defecto de operaciones: excluye los borrados (soft-delete, C4).

    ``Transaction.objects`` es la única puerta de operaciones VIVAS; los
    borrados solo son visibles vía ``Transaction.all_objects`` (administración
    y auditoría).
    """

    def get_queryset(self):
        """Solo operaciones no borradas."""
        return super().get_queryset().filter(is_deleted=False)

#: Dirección del flujo de dinero de la operación.
TRANSACTION_TYPES = [
    ("cobro", "Cobro (ingreso)"),
    ("pago", "Pago (egreso)"),
    ("transferencia", "Transferencia entre cuentas"),
]

#: Fuente de la tasa usada en una transferencia entre monedas distintas.
TRANSFER_RATE_SOURCES = [
    ("oficial", "Tasa oficial (BCV)"),
    ("manual", "Tasa personalizada"),
]

#: Estados persistentes de la operación (Pendiente/Pagado/Cancelado).
#: "Retrasado" es un estado derivado (ver ``is_overdue``).
TRANSACTION_STATES = [
    ("pendiente", "Pendiente"),
    ("pagado", "Pagado"),
    ("cancelado", "Cancelado"),
]

#: Fuente de la tasa usada para la conversión a USD.
SOURCE_TASA_CHOICES = [
    ("oficial", "Tasa oficial (BCV) vía DolarApi"),
    ("usd", "Operación en USD (tasa 1)"),
    ("manual", "Tasa manual"),
    ("fallback", "Tasa de emergencia (sin API)"),
]


class Category(OwnedModel):
    """Categoría de operaciones (ingreso o egreso).

    Las categorías por defecto se crean al registrar el usuario (señal
    ``signals``); el usuario puede añadir las suyas.
    """

    TIPO_CATEGORY = [
        ("ingreso", "Ingreso"),
        ("egreso", "Egreso"),
    ]

    name = models.CharField(max_length=60, verbose_name="Nombre")
    icon = models.CharField(max_length=40, blank=True, default="tag", verbose_name="Icono")
    tipo = models.CharField(max_length=10, choices=TIPO_CATEGORY, default="egreso", verbose_name="Tipo")
    is_default = models.BooleanField(default=False, verbose_name="Por defecto")

    class Meta:
        verbose_name = "Categoría"
        verbose_name_plural = "Categorías"
        ordering = ["tipo", "name"]
        constraints = [
            models.UniqueConstraint(fields=["user", "name", "tipo"], name="uniq_category_per_user")
        ]

    def __str__(self) -> str:
        """Representación: nombre."""
        return self.name


class Contact(OwnedModel):
    """Persona o entidad con la que se realizan operaciones recurrentes."""

    name = models.CharField(max_length=100, verbose_name="Nombre")
    note = models.CharField(max_length=200, blank=True, verbose_name="Nota")

    class Meta:
        verbose_name = "Contacto"
        verbose_name_plural = "Contactos"
        ordering = ["name"]

    def __str__(self) -> str:
        """Representación: nombre."""
        return self.name


class Transaction(OwnedModel):
    """Operación de cobro (ingreso) o pago (egreso) del usuario.

    Campos destacados:
        monto: cantidad en la moneda original.
        monto_usd/tasa_usd/fuente_tasa: conversión congelada a USD.
        estado: pendiente / pagado / cancelado.
        fecha_vencimiento: si existe y pasado + pendiente => retrasado.
        wallet: billetera asociada (misma moneda que la operación).
    """

    tipo = models.CharField(max_length=13, choices=TRANSACTION_TYPES, verbose_name="Tipo")
    estado = models.CharField(
        max_length=12, choices=TRANSACTION_STATES, default="pendiente", verbose_name="Estado"
    )
    monto = models.DecimalField(max_digits=20, decimal_places=MONEY_DECIMALS, verbose_name="Monto")
    moneda = models.CharField(max_length=3, choices=CURRENCY_CHOICES, verbose_name="Moneda")
    is_deleted = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name="Borrada",
        help_text="Soft-delete (C4): la operación se oculta de la API pero conserva su historial.",
    )

    objects = TransactionManager()
    all_objects = models.Manager()

    # Conversión congelada a USD (nunca se recalcula; R2/R4).
    monto_usd = models.DecimalField(max_digits=20, decimal_places=MONEY_DECIMALS, default=0, verbose_name="Monto en USD")
    tasa_usd = models.DecimalField(max_digits=20, decimal_places=4, default=1, verbose_name="Tasa usada")
    fuente_tasa = models.CharField(
        max_length=10, choices=SOURCE_TASA_CHOICES, default="fallback", verbose_name="Fuente de tasa"
    )

    concepto = models.CharField(max_length=160, blank=True, verbose_name="Concepto")
    contact = models.ForeignKey(
        Contact,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions",
        verbose_name="Contacto",
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions",
        verbose_name="Categoría",
    )
    wallet = models.ForeignKey(
        "wallets.Wallet",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions",
        verbose_name="Billetera",
    )
    # --- Campos de transferencia entre cuentas (tipo "transferencia") -------
    # ``wallet`` es la cuenta origen; ``dest_wallet`` la cuenta destino.
    # ``monto``/``moneda`` son de la cuenta origen; ``monto_destino``/``moneda_destino``
    # son el resultado aplicado a la cuenta destino (con la tasa usada).
    dest_wallet = models.ForeignKey(
        "wallets.Wallet",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="incoming_transfers",
        verbose_name="Billetera destino",
    )
    monto_destino = models.DecimalField(
        max_digits=20, decimal_places=MONEY_DECIMALS, default=0, verbose_name="Monto en destino"
    )
    moneda_destino = models.CharField(
        max_length=3, blank=True, choices=CURRENCY_CHOICES, verbose_name="Moneda destino"
    )
    tasa_uso = models.DecimalField(
        max_digits=20, decimal_places=4, default=1, verbose_name="Tasa usada en el traspaso"
    )
    tasa_fuente = models.CharField(
        max_length=10, choices=TRANSFER_RATE_SOURCES, default="manual", verbose_name="Fuente de la tasa"
    )
    fecha = models.DateField(default=date.today, verbose_name="Fecha")
    fecha_vencimiento = models.DateField(null=True, blank=True, verbose_name="Vence el")
    fecha_pagado = models.DateTimeField(null=True, blank=True, verbose_name="Pagado el")
    remind_me = models.BooleanField(
        default=True,
        verbose_name="Recordar",
        help_text="Sobrescribe la regla global de recordatorios si está desactivado.",
    )
    reminder_days = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="Avisar N días antes",
        help_text="Anticipación del recordatorio; si queda vacío se usa la regla global del usuario (ADR-09).",
    )
    nota = models.TextField(blank=True, verbose_name="Nota")

    class Meta:
        verbose_name = "Operación"
        verbose_name_plural = "Operaciones"
        ordering = ["-fecha"]
        default_manager_name = "objects"
        indexes = [
            models.Index(fields=["user", "estado"]),
            models.Index(fields=["user", "fecha_vencimiento"]),
            models.Index(fields=["user", "fecha"]),
            # A9: "pagos recientes" del dashboard (user + estado, orden por
            # fecha de pago descendente) y agregaciones por tipo+rango de fecha.
            models.Index(fields=["user", "estado", "-fecha_pagado"]),
            models.Index(fields=["user", "tipo", "fecha"]),
        ]
        constraints = [
            # A10: integridad a nivel de motor (la API ya valida; esto es el
            # respaldo en BD para cualquier escritura que la salte).
            models.CheckConstraint(
                condition=models.Q(monto__gt=0),
                name="transaction_monto_gt_0",
                violation_error_message="El monto debe ser mayor a cero.",
            ),
            models.CheckConstraint(
                condition=models.Q(tasa_usd__gt=0),
                name="transaction_tasa_usd_gt_0",
                violation_error_message="La tasa usada debe ser mayor a cero.",
            ),
            models.CheckConstraint(
                condition=models.Q(estado__in=["pendiente", "pagado", "cancelado"]),
                name="transaction_estado_valid",
                violation_error_message="Estado de operación inválido.",
            ),
            models.CheckConstraint(
                condition=models.Q(tipo__in=["cobro", "pago", "transferencia"]),
                name="transaction_tipo_valid",
                violation_error_message="Tipo de operación inválido.",
            ),
            models.CheckConstraint(
                condition=models.Q(fecha_vencimiento__isnull=True)
                | models.Q(fecha_vencimiento__gte=models.F("fecha")),
                name="transaction_vencimiento_gte_fecha",
                violation_error_message="El vencimiento no puede ser anterior a la fecha.",
            ),
        ]

    def __str__(self) -> str:
        """Representación: tipo+monto+concepto."""
        return f"{self.get_tipo_display()} {self.monto} {self.moneda} · {self.concepto or '—'}"

    def soft_delete(self) -> "Transaction":
        """Soft-delete (C4): oculta la operación de la API sin perder historial.

        El registro permanece en BD (visible solo con ``all_objects``) para
        auditoría; si el flujo lo requiere, la billetera ya fue revertida por
        el caller antes de invocar esto.
        """
        self.is_deleted = True
        self.save(update_fields=["is_deleted", "updated_at"])
        return self

    # ------------------------------------------------------------------
    # Propiedades de negocio
    # ------------------------------------------------------------------
    @property
    def is_overdue(self) -> bool:
        """True si la operación está pendiente y ha sobrepasado su vencimiento.

        Compara en la zona del usuario (se usa ``user.timezone_name``); si no hay
        ``fecha_vencimiento`` nunca está retrasada.
        """
        if self.estado != "pendiente" or self.fecha_vencimiento is None:
            return False
        today = timezone.localdate()
        return self.fecha_vencimiento < today

    @property
    def effective_state(self) -> str:
        """Estado efectivo: devuelve ``retrasado`` cuando corresponde.

        Nota: en el MVP el calendario "hoy" usa la timezone del servidor; la
        zona del usuario se aplica en los endpoints cuando sea necesario.
        """
        return "retrasado" if self.is_overdue else self.estado

    @property
    def signed_amount(self) -> Decimal:
        """Cantidad con signo según el flujo (cobro +, pago -).

        Útil para consolidaciones del dashboard (el signo indica dirección).

        Returns:
            ``monto`` positivo para cobros, negativo para pagos.
        """

        return self.monto if self.tipo == "cobro" else -self.monto