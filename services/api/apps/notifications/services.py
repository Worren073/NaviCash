"""services — Generación de notificaciones según el estado del dominio.

Al consultar ``GET /api/notifications`` se evalúa el estado actual y se crean
las alertas que aún no existan (deduplicadas por ``kind`` + referencia en
``extra``), para no repetir la misma alerta cada vez; el estado "leída" lo
gestiona el usuario sin regenerar notificaciones nuevas.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from apps.notifications.models import Notification
from apps.savings.models import SavingsGoal
from apps.transactions.models import Transaction


def _reminder_days(tx: Transaction, user) -> int:
    """Anticipación del aviso: la de la operación o la regla global del usuario."""
    if tx.reminder_days is not None:
        return tx.reminder_days
    return getattr(user, "reminder_days", 3) or 0


def _notify_once(user, kind: str, ident: dict, title: str, message: str) -> None:
    """Crea la notificación solo si no existe otra igual (leída o no)."""
    exists = Notification.objects.filter(
        user=user, kind=kind, extra=ident
    ).exists()
    if exists:
        return
    Notification.objects.create(
        user=user, kind=kind, title=title, message=message, extra=ident
    )


def refresh_notifications(user, today: date | None = None) -> list[Notification]:
    """Evalúa el dominio y crea las alertas pendientes del usuario.

    Args:
        user: usuario autenticado.
        today: fecha de referencia (inyectable en tests; por defecto hoy).

    Returns:
        Lista de las 30 notificaciones más recientes del usuario.
    """
    today = today or date.today()

    # 1) Operaciones pendientes con vencimiento próximo o ya vencidas.
    pending = Transaction.objects.filter(
        user=user, estado="pendiente", fecha_vencimiento__isnull=False
    )
    for tx in pending:
        due = tx.fecha_vencimiento
        label = tx.concepto or tx.get_tipo_display()
        if due < today:
            _notify_once(
                user,
                "overdue",
                {"transaction_id": str(tx.id)},
                title=f"«{label}» venció",
                message=f"Venció el {due.isoformat()} sin registrarse como pagado.",
            )
        elif due <= today + timedelta(days=_reminder_days(tx, user)):
            _notify_once(
                user,
                "due_soon",
                {"transaction_id": str(tx.id)},
                title=f"«{label}» vence pronto",
                message=f"Vence el {due.isoformat()}.",
            )

    # 2) Metas de ahorro alcanzadas.
    for goal in SavingsGoal.objects.filter(user=user):
        if goal.total_contributed >= goal.target_amount:
            _notify_once(
                user,
                "goal_reached",
                {"goal_id": str(goal.id)},
                title=f"¡Meta «{goal.name}» alcanzada!",
                message=f"Completaste el objetivo de {goal.target_amount} {goal.currency}.",
            )

    return list(
        Notification.objects.filter(user=user).order_by("-created_at")[:30]
    )
