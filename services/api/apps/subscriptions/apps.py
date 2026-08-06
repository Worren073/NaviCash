"""Configuración de la app ``subscriptions``."""

from django.apps import AppConfig


class SubscriptionsConfig(AppConfig):
    """AppConfig de ``subscriptions``: mensualidades con avance por tiempo."""

    name = "apps.subscriptions"
    verbose_name = "Mensualidades"
