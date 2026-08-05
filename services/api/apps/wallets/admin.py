"""admin — Registro de billeteras en el panel de administración."""

from django.contrib import admin

from apps.wallets.models import Wallet


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    """Admin: billeteras con su saldo actual."""

    list_display = ("name", "currency", "saldo", "tipo", "user", "created_at")
    list_filter = ("currency", "tipo")
    search_fields = ("name", "user__email")
    readonly_fields = ("created_at", "updated_at")