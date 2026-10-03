"""admin — Registro de modelos del CRM."""

from django.contrib import admin

from apps.crm.models import BusinessContact, Invoice, InvoiceItem, InvoicePayment


@admin.register(BusinessContact)
class BusinessContactAdmin(admin.ModelAdmin):
    """Admin de contactos del negocio."""

    list_display = ["name", "business", "type", "customer_type", "phone", "is_active"]
    list_filter = ["type", "customer_type", "is_active"]
    search_fields = ["name", "email", "phone", "tax_id"]
    ordering = ["name"]


class InvoiceItemInline(admin.TabularInline):
    """Líneas de factura en el admin."""

    model = InvoiceItem
    extra = 0


class InvoicePaymentInline(admin.TabularInline):
    """Pagos de factura en el admin."""

    model = InvoicePayment
    extra = 0


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    """Admin de facturas."""

    list_display = ["number", "contact", "status", "total", "balance_due", "due_date"]
    list_filter = ["status", "currency"]
    search_fields = ["number", "contact__name"]
    ordering = ["-issue_date"]
    inlines = [InvoiceItemInline, InvoicePaymentInline]


@admin.register(InvoiceItem)
class InvoiceItemAdmin(admin.ModelAdmin):
    """Admin de líneas de factura."""

    list_display = ["invoice", "description", "quantity", "unit_price", "total"]


@admin.register(InvoicePayment)
class InvoicePaymentAdmin(admin.ModelAdmin):
    """Admin de pagos de factura."""

    list_display = ["invoice", "amount", "paid_at"]
