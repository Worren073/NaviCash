"""recalc_overdue — Comando de gestión: reitera la coherencia de estados.

El estado "retrasado" se calcula en lectura (ver ``Transaction.is_overdue``),
así que este comando no es imprescindible para corregir datos, pero sirve para
tareas de mantenimiento/auditoría: recorre operaciones pendientes vencidas y
las entrega listadas; en el MVP no persiste cambios.

Uso:
    python manage.py recalc_overdue
Se invoca desde el cron de Render para actividades de reporte/métricas.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.transactions.models import Transaction


class Command(BaseCommand):
    """Comando Django de auditoría de operaciones retrasadas."""

    help = "Lista operaciones pendientes vencidas (estado derivado 'retrasado')."

    def handle(self, *args, **options) -> None:
        """Revisa y reporta las operaciones retrasadas."""
        today = timezone.localdate()
        overdue = Transaction.objects.filter(estado="pendiente", fecha_vencimiento__lt=today)
        self.stdout.write(
            self.style.SUCCESS(f"Operaciones retrasadas al {today}: {overdue.count()}")
        )
        for tx in overdue.select_related("wallet")[:20]:
            self.stdout.write(f"  · {tx}")