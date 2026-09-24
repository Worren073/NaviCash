"""admin — Registro de ``checklists`` en el panel de administración."""

from django.contrib import admin

from apps.checklists.models import ListItem, ShoppingList


class ListItemInline(admin.TabularInline):
    """Productos de la lista en el mismo formulario."""

    model = ListItem
    extra = 0


@admin.register(ShoppingList)
class ShoppingListAdmin(admin.ModelAdmin):
    """Admin: listas de compras de los usuarios."""

    list_display = ("name", "user", "estado", "currency", "total_real", "completed_at")
    list_filter = ("estado", "currency")
    search_fields = ("name", "user__email")
    inlines = [ListItemInline]
    readonly_fields = ("created_at", "updated_at")