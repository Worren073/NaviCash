"""services — Generación de notificaciones según el estado del dominio.

Al consultar ``GET /api/notifications`` se evalúa el estado actual y se crean
las alertas que aún no existan (deduplicadas por ``kind`` + referencia en
``extra``), para no repetir la misma alerta cada vez; el estado "leída" lo
gestiona el usuario sin regenerar notificaciones nuevas.

Rendimiento (AUDIT A8/M5): las candidatas se calculan primero y las que faltan
se crean en UNA sola pasada con ``bulk_create(ignore_conflicts=True)``, apoyado
en el índice único ``(user, kind, extra)``: ni un ``exists()`` por fila, ni
duplicados bajo concurrencia (los INSERT en conflicto se descartan).
"""

from __future__ import annotations

import json
from datetime import date, timedelta

from apps.notifications.models import Notification
from apps.savings.models import SavingsGoal
from apps.transactions.models import Transaction


def _reminder_days(tx: Transaction, user) -> int:
    """Anticipación del aviso: la de la operación o la regla global del usuario."""
    if tx.reminder_days is not None:
        return tx.reminder_days
    return getattr(user, "reminder_days", 3) or 0


def _candidates(user, today: date) -> list[dict]:
    """Evalúa el dominio y lista las alertas que deberían existir.

    Returns:
        Lista de dicts ``{"kind", "extra", "title", "message"}``, sin tocar
        la BD de notificaciones.
    """
    items: list[dict] = []

    # 1) Operaciones pendientes con vencimiento próximo o ya vencidas.
    pending = Transaction.objects.filter(
        user=user, estado="pendiente", fecha_vencimiento__isnull=False
    )
    for tx in pending:
        due = tx.fecha_vencimiento
        label = tx.concepto or tx.get_tipo_display()
        if due < today:
            items.append(
                {
                    "kind": "overdue",
                    "extra": {"transaction_id": str(tx.id)},
                    "title": f"«{label}» venció",
                    "message": f"Venció el {due.isoformat()} sin registrarse como pagado.",
                }
            )
        elif due <= today + timedelta(days=_reminder_days(tx, user)):
            items.append(
                {
                    "kind": "due_soon",
                    "extra": {"transaction_id": str(tx.id)},
                    "title": f"«{label}» vence pronto",
                    "message": f"Vence el {due.isoformat()}.",
                }
            )

    # 2) Metas de ahorro alcanzadas.
    for goal in SavingsGoal.objects.filter(user=user):
        if goal.total_contributed >= goal.target_amount:
            items.append(
                {
                    "kind": "goal_reached",
                    "extra": {"goal_id": str(goal.id)},
                    "title": f"¡Meta «{goal.name}» alcanzada!",
                    "message": (
                        f"Completaste el objetivo de {goal.target_amount} {goal.currency}."
                    ),
                }
            )

    return items


def _notify_missing(user, candidates: list[dict]) -> None:
    """Crea en una sola pasada las notificaciones que aún no existen.

    La existencia se comprueba con UNA query sobre los pares (kind, extra)
    ya persistidos; la creación es un único ``bulk_create`` cuyo
    ``ignore_conflicts`` absorbe las carreras entre GETs concurrentes (el
    índice único de ``Notification.Meta`` es la garantía real).
    """
    kinds = {c["kind"] for c in candidates}
    existing = {
        (kind, json.dumps(extra, sort_keys=True))
        for kind, extra in Notification.objects.filter(user=user, kind__in=kinds)
        .values_list("kind", "extra")
    }
    missing = [
        Notification(user=user, kind=c["kind"], title=c["title"], message=c["message"], extra=c["extra"])
        for c in candidates
        if (c["kind"], json.dumps(c["extra"], sort_keys=True)) not in existing
    ]
    Notification.objects.bulk_create(missing, ignore_conflicts=True)


def refresh_notifications(user, today: date | None = None) -> list[Notification]:
    """Evalúa el dominio y crea las alertas pendientes del usuario.

    Args:
        user: usuario autenticado.
        today: fecha de referencia (inyectable en tests; por defecto hoy).

    Returns:
        Lista de las 30 notificaciones más recientes del usuario.
    """
    today = today or date.today()
    _notify_missing(user, _candidates(user, today))

    return list(
        Notification.objects.filter(user=user).order_by("-created_at")[:30]
    )