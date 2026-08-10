"""purge_blacklist — Retención de la blacklist de SimpleJWT (AUDIT M5).

Uso:
    python manage.py purge_blacklist [--batch 500]

Borra en lotes los ``OutstandingToken`` expirados (``expires_at < now``); el
borrado en cascada elimina también sus ``BlacklistedToken`` asociados. Los
tokens expirados ya no pueden refrescarse ni completar un logout, así que
solo ocupan espacio.

Programación sugerida (cron diario):
    0 4 * * *  cd services/api && python manage.py purge_blacklist --batch 500
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken


class Command(BaseCommand):
    """Comando Django de purga de tokens JWT expirados."""

    help = "Elimina en lotes los tokens JWT expirados de la blacklist."

    def add_arguments(self, parser) -> None:
        """Argumento opcional ``--batch`` (default 500)."""
        parser.add_argument(
            "--batch",
            type=int,
            default=500,
            help="Máximo de filas por lote de borrado (default: 500).",
        )

    def handle(self, *args, **options) -> None:
        """Purgas por lotes hasta agotar los expirados."""
        batch = max(1, options["batch"])
        now = timezone.now()
        total = 0
        while True:
            expired_ids = list(
                OutstandingToken.objects.filter(expires_at__lt=now)
                .values_list("id", flat=True)[:batch]
            )
            if not expired_ids:
                break
            deleted, _ = OutstandingToken.objects.filter(id__in=expired_ids).delete()
            total += deleted
        self.stdout.write(
            self.style.SUCCESS(f"Tokens JWT expirados eliminados: {total}")
        )