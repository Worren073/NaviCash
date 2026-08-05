"""admin — Registro de modelos para el panel de administración (dev/troubleshoot)."""

from django.contrib import admin

from apps.shortcuts.models import Shortcut


@admin.register(Shortcut)
class ShortcutAdmin(admin.ModelAdmin):
    """Admin: atajos del home (solo lectura de config JSON, edición simple)."""

    list_display = ("label", "kind", "icon", "order", "user", "created_at")
    list_filter = ("kind",)
    search_fields = ("label", "user__email")
    ordering = ("order",)
    readonly_fields = ("created_at", "updated_at")