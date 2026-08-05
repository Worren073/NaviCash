"""Configuración de la app ``wallets``."""

from django.apps import AppConfig


class WalletsConfig(AppConfig):
    """AppConfig de ``wallets``: billeteras y saldos."""

    name = "apps.wallets"
    verbose_name = "Billeteras"