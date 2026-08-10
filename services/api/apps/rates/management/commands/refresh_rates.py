"""refresh_rates — Comando de gestión: actualiza la tasa oficial del dólar.

Uso:
    python manage.py refresh_rates
    python manage.py refresh_rates --if-stale --retention-days 180

Ejecutado por el cron de Render (cada 1 h) y al arrancar el contenedor de
desarrollo. Con ``--provider static`` fuerza el proveedor estático (tests).

Opciones de operación (A5/M5):
- ``--retention-days N``: borra las tasas guardadas hace más de N días
  (default 180), cumpliendo la retención de ``ExchangeRate`` (M5).
- ``--if-stale``: no consulta al proveedor si ya existe una tasa fresca
  (con menos de ``RATE_TTL_MINUTES`` de antigüedad), para no golpear la API
  cuando otro proceso ya refrescó hace poco.
"""

from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.rates.models import ExchangeRate
from apps.rates.providers import RateProviderError
from apps.rates.service import _is_fresh, refresh_official_rate


class Command(BaseCommand):
    """Comando Django para refrescar la tasa oficial desde DolarApi."""

    help = "Consulta DolarApi y guarda la tasa oficial del dólar (BCV)."

    def add_arguments(self, parser) -> None:
        """Define las opciones de retención y refresco condicional."""
        parser.add_argument(
            "--retention-days",
            type=int,
            default=180,
            help="Borra tasas guardadas hace más de N días (default: 180).",
        )
        parser.add_argument(
            "--if-stale",
            action="store_true",
            help="Solo consulta al proveedor si la última tasa guardada ya "
            "no es fresca (supera el TTL de RATE_TTL_MINUTES).",
        )

    def handle(self, *args, **options) -> None:
        """Ejecuta la actualización y la retención; escribe el resultado."""
        if options["if_stale"] and self._latest_is_fresh():
            self.stdout.write(
                self.style.WARNING(
                    "Tasa oficial ya fresca (--if-stale): no se consulta al proveedor."
                )
            )
        else:
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

        purged = self._purge_older_than(options["retention_days"])
        if purged:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Retención: {purged} tasas antiguas eliminadas "
                    f"(más de {options['retention_days']} días)."
                )
            )

    def _latest_is_fresh(self) -> bool:
        """True si la última tasa oficial guardada aún está dentro del TTL."""
        ttl = getattr(settings, "RATE_TTL_MINUTES", 60)
        latest = (
            ExchangeRate.objects.filter(source="oficial")
            .order_by("-input_at")
            .first()
        )
        return latest is not None and _is_fresh(latest, ttl)

    def _purge_older_than(self, retention_days: int) -> int:
        """Borra las tasas con ``input_at`` anterior al corte y devuelve el total."""
        if retention_days <= 0:
            return 0
        cutoff = timezone.now() - timedelta(days=retention_days)
        deleted, _ = ExchangeRate.objects.filter(input_at__lt=cutoff).delete()
        return deleted
