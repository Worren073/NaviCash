"""Configuración de la app ``transactions``."""

from django.apps import AppConfig


class TransactionsConfig(AppConfig):
    """AppConfig de ``transactions``: cobros y pagos."""

    name = "apps.transactions"
    verbose_name = "Cobros y pagos"

    def ready(self) -> None:
        """Registra las señales de la app al iniciar Django.

        ``bootstrap_hooks`` crea las categorías por defecto cuando se registra
        un usuario nuevo.
        """
        from apps.transactions import signals  # noqa: F401