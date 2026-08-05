"""admin — Registro del modelo ``User`` en el panel de administración."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from apps.accounts.models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """Admin de usuarios con los campos personalizados en la vista."""

    fieldsets = DjangoUserAdmin.fieldsets + (
        ("Preferencias NaviCash", {"fields": ("base_currency", "timezone_name", "reminder_days")}),
    )
    list_display = ("email", "is_active", "is_verified", "base_currency", "date_joined")
    list_filter = ("is_active",)
    ordering = ("-date_joined",)