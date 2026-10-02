"""admin — Registro del modelo Business en el panel de administración."""

from django.contrib import admin

from apps.business.models import Business


@admin.register(Business)
class BusinessAdmin(admin.ModelAdmin):
    """Administración del negocio: lectura de identidad y dueño."""

    list_display = ("name", "currency", "user", "created_at")
    search_fields = ("name", "user__email")
    readonly_fields = ("created_at", "updated_at")