"""admin — Registro de modelos del CRM."""

from django.contrib import admin

from apps.crm.models import BusinessContact


@admin.register(BusinessContact)
class BusinessContactAdmin(admin.ModelAdmin):
    """Admin de contactos del negocio."""

    list_display = ["name", "business", "type", "customer_type", "phone", "is_active"]
    list_filter = ["type", "customer_type", "is_active"]
    search_fields = ["name", "email", "phone", "tax_id"]
    ordering = ["name"]
