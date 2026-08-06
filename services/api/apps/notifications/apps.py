"""Configuración de la app ``notifications``."""

from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    """AppConfig de ``notifications``: alertas generadas para el usuario."""

    name = "apps.notifications"
    verbose_name = "Notificaciones"
