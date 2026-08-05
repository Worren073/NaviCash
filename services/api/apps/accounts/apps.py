"""accounts — Configuración de app."""

from django.apps import AppConfig


class AccountsConfig(AppConfig):
    """AppConfig de ``accounts``: usuarios y autenticación."""

    name = "apps.accounts"
    verbose_name = "Cuentas y autenticación"