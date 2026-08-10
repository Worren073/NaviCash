"""purge_notifications — Retención de notificaciones leídas (AUDIT M5).

Uso:
    python manage.py purge_notifications [--days 90]

Borra las notificaciones marcadas como leídas con más de ``--days`` de
antigüedad (default 90). Las no leídas y las recientes se conservan.

Programación sugerida (cron diario):
    0 3 * * *  cd services/api && python manage.py purge_notifications --days 90
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.notifications.models import Notification


class Command(BaseCommand):
    """Comando Django de retención de notificaciones leídas antiguas."""

    help = "Elimina notificaciones leídas con más de --days de antigüedad."

    def add_arguments(self, parser) -> None:
        """Argumento opcional ``--days`` (default 90)."""
        parser.add_argument(
            "--days",
            type=int,
            default=90,
            help="Antigüedad mínima en días de las leídas a borrar (default: 90).",
        )

    def handle(self, *args, **options) -> None:
        """Borra las leídas antiguas e informa cuántas se eliminaron."""
        cutoff = timezone.now() - timedelta(days=options["days"])
        deleted, _ = Notification.objects.filter(
            read=True, created_at__lt=cutoff
        ).delete()
        self.stdout.write(
            self.style.SUCCESS(
                f"Notificaciones leídas anteriores a {cutoff.isoformat()} "
                f"eliminadas: {deleted}"
            )
        )