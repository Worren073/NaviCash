"""Configuración de la app ``rates``."""

from django.apps import AppConfig


class RatesConfig(AppConfig):
    """AppConfig de ``rates``: tasas de cambio y DolarApi."""

    name = "apps.rates"
    verbose_name = "Tasas de cambio"