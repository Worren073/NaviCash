"""Configuración de la app ``business``."""

from django.apps import AppConfig


class BusinessConfig(AppConfig):
    """AppConfig de ``business``: módulo de negocio del usuario."""

    name = "apps.business"
    verbose_name = "Negocio"