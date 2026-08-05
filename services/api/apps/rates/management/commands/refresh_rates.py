"""refresh_rates — Comando de gestión: actualiza la tasa oficial del dólar.

Uso:
    python manage.py refresh_rates

Ejecutado por el cron de Render (cada 1 h) y al arrancar el contenedor de
desarrollo. Con ``--provider static`` fuerza el proveedor estático (tests).
"""

from django.core.management.base import BaseCommand, CommandError

from apps.rates.providers import RateProviderError
from apps.rates.service import refresh_official_rate


class Command(BaseCommand):
    """Comando Django para refrescar la tasa oficial desde DolarApi."""

    help = "Consulta DolarApi y guarda la tasa oficial del dólar (BCV)."

    def handle(self, *args, **options) -> None:
        """Ejecuta la actualización y escribe el resultado por consola."""
        try:
            rate = refresh_official_rate()
        except RateProviderError as exc:
            raise CommandError(f"No se pudo refrescar la tasa: {exc}") from exc
        self.stdout.write(
            self.style.SUCCESS(
                f"Tasa oficial guardada: {rate.currency} {rate.effective_rate} "
                f"(fuente={rate.source}, fecha={rate.rate_date.isoformat()})"
            )
        )