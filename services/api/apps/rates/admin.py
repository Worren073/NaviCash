"""admin — Registro de ``ExchangeRate`` en el panel de administración."""

from django.contrib import admin

from apps.rates.models import ExchangeRate


@admin.register(ExchangeRate)
class ExchangeRateAdmin(admin.ModelAdmin):
    """Admin: historial de tasas (lectura para auditoría de conversiones)."""

    list_display = ("currency", "source", "promedio", "rate_date", "input_at", "is_stale")
    list_filter = ("source", "currency", "is_stale")
    search_fields = ("currency",)
    date_hierarchy = "rate_date"
    readonly_fields = ("input_at",)