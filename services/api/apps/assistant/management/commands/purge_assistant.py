"""purge_assistant — Comando de gestión: retención del historial del chat (M5).

Uso programable (cron diario, ej. 03:00 UTC):

    python manage.py purge_assistant --days 180

Borra los ``ChatMessage`` más viejos que ``--days`` (default 180) en lotes de
1000 para no mantener transacciones largas ni bloquear la tabla. Otra
alternativa de schedulers (Heroku Scheduler, Render cron, systemd timer):
misma línea de comando, con la opción de retención deseada.
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.assistant.models import ChatMessage

#: Tamaño de cada lote de borrado (evita transacciones largas).
PURGE_BATCH_SIZE = 1000


class Command(BaseCommand):
    """Comando Django para purgar los mensajes del chat vencidos."""

    help = "Borra los mensajes del asistente más viejos que --days (default: 180)."

    def add_arguments(self, parser) -> None:
        """Define la antigüedad mínima de los mensajes a borrar."""
        parser.add_argument(
            "--days",
            type=int,
            default=180,
            help="Edad mínima (en días) de un mensaje para ser borrado (default: 180).",
        )

    def handle(self, *args, **options) -> None:
        """Purga por lotes los mensajes vencidos y reporta el total."""
        days = options["days"]
        if days <= 0:
            self.stdout.write(self.style.WARNING("--days debe ser mayor a 0; no se borró nada."))
            return

        cutoff = timezone.now() - timedelta(days=days)
        stale_qs = ChatMessage.objects.filter(created_at__lt=cutoff)

        deleted = 0
        while True:
            ids = list(stale_qs.values_list("pk", flat=True)[:PURGE_BATCH_SIZE])
            if not ids:
                break
            batch_deleted, _ = ChatMessage.objects.filter(pk__in=ids).delete()
            deleted += batch_deleted

        self.stdout.write(
            self.style.SUCCESS(
                f"Retención de chat: {deleted} mensaje(s) borrados"
                f" (anteriores a {cutoff.strftime('%Y-%m-%d')}, más de {days} días)."
            )
        )