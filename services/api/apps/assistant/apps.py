"""Configuración de la app ``assistant``."""

from django.apps import AppConfig


class AssistantConfig(AppConfig):
    """AppConfig de ``assistant``: asistente conversacional Navi."""

    name = "apps.assistant"
    verbose_name = "Asistente"