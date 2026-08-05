"""Configuración de la app ``savings``."""

from django.apps import AppConfig


class SavingsConfig(AppConfig):
    """AppConfig de ``savings``: metas de ahorro y aportes."""

    name = "apps.savings"
    verbose_name = "Ahorro y metas"