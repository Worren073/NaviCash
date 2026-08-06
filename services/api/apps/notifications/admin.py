"""admin — Registro de ``Notification`` en el panel de administración."""

from django.contrib import admin

from apps.notifications.models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    """Admin: notificaciones generadas para los usuarios."""

    list_display = ("title", "kind", "read", "user", "created_at")
    list_filter = ("kind", "read")
    search_fields = ("title", "message", "user__email")
    readonly_fields = ("created_at", "updated_at")