"""admin — Registro de ``Subscription`` en el panel de administración."""

from django.contrib import admin

from apps.subscriptions.models import Subscription


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    """Admin: mensualidades de los usuarios."""

    list_display = ("name", "start_date", "end_date", "user", "created_at")
    list_filter = ("start_date",)
    search_fields = ("name", "user__email")
    readonly_fields = ("created_at", "updated_at")