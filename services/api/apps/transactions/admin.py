"""admin — Registro de operaciones para el panel de administración."""

from django.contrib import admin

from apps.transactions.models import Category, Contact, Transaction


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    """Admin: operaciones con su conversión USD congelada."""

    list_display = ("concepto", "tipo", "monto", "moneda", "estado", "fecha_vencimiento", "user")
    list_filter = ("tipo", "estado", "moneda")
    search_fields = ("concepto", "nota", "user__email")
    readonly_fields = ("monto_usd", "tasa_usd", "fuente_tasa", "created_at", "updated_at")


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    """Admin: categorías con su tipo (ingreso/egreso)."""

    list_display = ("name", "tipo", "is_default", "user")
    list_filter = ("tipo", "is_default")
    search_fields = ("name", "user__email")


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    """Admin: contactos del usuario."""

    list_display = ("name", "user")
    search_fields = ("name", "user__email")