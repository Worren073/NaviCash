"""purge_deleted_users — Purga definitiva de cuentas con gracia vencida.

Uso:
    python manage.py purge_deleted_users

Borra las cuentas cuyo ``deletion_scheduled_at`` ya pasó: primero sus filas de
``BalanceAuditLog`` (FK SET_NULL, no cascadean) y después el usuario, cuyo
``delete()`` dispara el CASCADE del resto de datos (wallets, transacciones,
metas, suscripciones, chats, notificaciones, tokens JWT…).

El disparador perezoso diario de ``MeView.get`` normalmente lo deja sin trabajo;
este comando existe para cron externo (Render Cron / crontab) y para forzar una
corrida manual.

Programación sugerida (cron diario):
    30 4 * * *  cd services/api && python manage.py purge_deleted_users
"""

from django.core.management.base import BaseCommand

from apps.accounts.services import purge_due_accounts


class Command(BaseCommand):
    """Comando Django de purga de cuentas eliminadas (gracia vencida)."""

    help = (
        "Elimina definitivamente las cuentas cuyo período de gracia de "
        "eliminación ya venció."
    )

    def handle(self, *args, **options) -> None:
        """Purga las cuentas vencidas e informa la cantidad."""
        deleted = purge_due_accounts()
        if deleted:
            self.stdout.write(
                self.style.SUCCESS(f"Cuentas eliminadas definitivamente: {deleted}")
            )
        else:
            self.stdout.write("No hay cuentas con período de gracia vencido.")
