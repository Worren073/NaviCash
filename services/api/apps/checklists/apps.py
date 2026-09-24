"""Configuración de la app ``checklists``."""

from django.apps import AppConfig


class ChecklistsConfig(AppConfig):
    """AppConfig de ``checklists``: listas de compras del mercado."""

    name = "apps.checklists"
    verbose_name = "Listas de compras"