"""Configuración de la app ``overview`` (resumen del dashboard)."""

from django.apps import AppConfig


class OverviewConfig(AppConfig):
    """AppConfig de ``overview``: agregado de resumen para la home."""

    name = "apps.overview"
    verbose_name = "Resumen"