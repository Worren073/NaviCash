"""send_push_reminders — Tick manual de generación + envío Web Push.

Equivalente a POST /api/internal/tick (que es el que dispara el cron
horario de GitHub Actions). Útil para pruebas y operaciones manuales.

    python manage.py send_push_reminders
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.notifications.services import tick


class Command(BaseCommand):
    """Genera alertas nuevas por usuario y empuja las notificaciones."""

    help = "Genera notificaciones nuevas y las envía vía Web Push."

    def handle(self, *args, **options) -> None:
        result = tick()
        if result is None:
            self.stdout.write(
                self.style.WARNING("Un ciclo anterior sigue en curso (lock activo).")
            )
            return
        self.stdout.write(
            self.style.SUCCESS(
                f"Tick completado: {result['users']} usuario(s), "
                f"{result['pushed']} push enviados."
            )
        )
