"""services — Generación y ENTREGA de notificaciones según el dominio.

Dos rutas de generación:

1. Perezosa (como siempre): al consultar ``GET /api/notifications`` se evalúa
   el estado actual y se crean las alertas que aún no existan (deduplicadas
   por ``kind`` + ``extra``, índice único), sin empujar nada.
2. Tick externo (Web Push): el endpoint ``POST /api/internal/tick`` (o el
   comando ``send_push_reminders``, o el workflow horario de GitHub Actions)
   recorre los usuarios con suscripción push, genera las alertas nuevas y las
   ENVÍA vía Web Push (VAPID). La deduplicación garantiza que cada alerta se
   empuje una sola vez aunque el tick corra cada hora.

Rendimiento (AUDIT A8/M5): las candidatas se calculan primero y las que faltan
se crean en UNA sola pasada con ``bulk_create(ignore_conflicts=True)``, apoyado
en el índice único ``(user, kind, extra)``: ni un ``exists()`` por fila, ni
duplicados bajo concurrencia (los INSERT en conflicto se descartan).
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, time as dt_time, timedelta, timezone as dt_timezone
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone as dj_timezone
from pywebpush import WebPushException, webpush

from apps.accounts.models import User
from apps.crm.models import Invoice, Product
from apps.notifications.models import Notification, PushSubscription
from apps.savings.models import SavingsGoal
from apps.transactions.models import Transaction

logger = logging.getLogger(__name__)

#: Lock anti-solapamiento del tick (dos ciclos nunca corren a la vez).
TICK_LOCK_KEY = "notifications:tick:running"
#: TTL del lock: si un ciclo muriera sin liberar, el siguiente reintenta en 10 min.
TICK_LOCK_TTL_SECONDS = 600

#: Zona horaria de respaldo si ``timezone_name`` del usuario es inválida.
_FALLBACK_TZ = "America/Caracas"


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
    ).select_related("wallet__business")
    for tx in pending:
        due = tx.fecha_vencimiento
        label = tx.concepto or tx.get_tipo_display()
        scope = "business" if tx.wallet and tx.wallet.business_id else "personal"
        if due < today:
            items.append(
                {
                    "kind": "overdue",
                    "scope": scope,
                    "extra": {"transaction_id": str(tx.id)},
                    "title": f"«{label}» venció",
                    "message": f"Venció el {due.isoformat()} sin registrarse como pagado.",
                }
            )
        elif due <= today + timedelta(days=_reminder_days(tx, user)):
            items.append(
                {
                    "kind": "due_soon",
                    "scope": scope,
                    "extra": {"transaction_id": str(tx.id)},
                    "title": f"«{label}» vence pronto",
                    "message": f"Vence el {due.isoformat()}.",
                }
            )

    # 2) Metas de ahorro alcanzadas (siempre personales en el MVP).
    for goal in SavingsGoal.objects.filter(user=user):
        if goal.total_contributed >= goal.target_amount:
            items.append(
                {
                    "kind": "goal_reached",
                    "scope": "personal",
                    "extra": {"goal_id": str(goal.id)},
                    "title": f"¡Meta «{goal.name}» alcanzada!",
                    "message": (
                        f"Completaste el objetivo de {goal.target_amount} {goal.currency}."
                    ),
                }
            )

    # 3) Facturas pendientes de cobro del negocio (vencidas o por vencer).
    from apps.crm.services import refresh_invoice_overdue_status

    invoices = Invoice.objects.filter(
        user=user,
        status__in=["enviada", "parcial"],
        due_date__isnull=False,
    ).select_related("contact")
    for inv in invoices:
        if inv.due_date < today:
            refresh_invoice_overdue_status(inv, today)
            items.append(
                {
                    "kind": "invoice_overdue",
                    "scope": "business",
                    "extra": {"invoice_id": str(inv.id)},
                    "title": f"Factura {inv.number} venció",
                    "message": (
                        f"«{inv.contact.name}» debe {inv.balance_due} {inv.currency} "
                        f"desde el {inv.due_date.isoformat()}."
                    ),
                }
            )
        elif inv.due_date <= today + timedelta(days=_reminder_days(inv, user)):
            items.append(
                {
                    "kind": "invoice_overdue",
                    "scope": "business",
                    "extra": {"invoice_id": str(inv.id), "upcoming": "1"},
                    "title": f"Factura {inv.number} vence pronto",
                    "message": (
                        f"«{inv.contact.name}» tiene un saldo de "
                        f"{inv.balance_due} {inv.currency} que vence el {inv.due_date.isoformat()}."
                    ),
                }
            )

    # 4) Stock bajo del inventario del negocio (una vez por día).
    for product in Product.objects.select_related("business").filter(
        user=user,
        is_active=True,
        low_stock_threshold__isnull=False,
    ):
        if product.stock_quantity <= product.low_stock_threshold:
            items.append(
                {
                    "kind": "product_low_stock",
                    "scope": "business",
                    "extra": {"product_id": str(product.id), "date": today.isoformat()},
                    "title": "Stock bajo",
                    "message": (
                        f"Quedan {product.stock_quantity} de «{product.name}» "
                        f"(mínimo {product.low_stock_threshold})."
                    ),
                }
            )

    return items


def _notify_missing(user, candidates: list[dict]) -> list[Notification]:
    """Crea en una sola pasada las notificaciones que aún no existen.

    La existencia se comprueba con UNA query sobre los pares (kind, extra)
    ya persistidos; la creación es un único ``bulk_create`` cuyo
    ``ignore_conflicts`` absorbe las carreras entre GETs concurrentes (el
    índice único de ``Notification.Meta`` es la garantía real).

    Returns:
        Las filas que ESTE llamado intentó crear (las nuevas desde el punto
        de vista del llamador; bajo carrera extrema alguna puede descartarse
        por conflicto, lo que solo implicaría un push menos, nunca duplicado).
    """
    kinds = {c["kind"] for c in candidates}
    scopes = {c["scope"] for c in candidates}
    existing = {
        (scope, kind, json.dumps(extra, sort_keys=True))
        for scope, kind, extra in Notification.objects.filter(
            user=user, kind__in=kinds, scope__in=scopes
        )
        .values_list("scope", "kind", "extra")
    }
    missing = [
        Notification(
            user=user,
            kind=c["kind"],
            scope=c["scope"],
            title=c["title"],
            message=c["message"],
            extra=c["extra"],
        )
        for c in candidates
        if (c["scope"], c["kind"], json.dumps(c["extra"], sort_keys=True)) not in existing
    ]
    Notification.objects.bulk_create(missing, ignore_conflicts=True)
    return missing


#: Máximo de notificaciones no leídas que se conservan visibles por ámbito.
MAX_TRAY_NOTIFICATIONS = 6


def refresh_notifications(
    user, scope: str = "personal", today: date | None = None
) -> list[Notification]:
    """Evalúa el dominio y crea las alertas pendientes del usuario para un ámbito.

    Args:
        user: usuario autenticado.
        scope: ámbito de notificación ("personal" o "business").
        today: fecha de referencia (inyectable en tests; por defecto hoy).

    Returns:
        Lista de hasta ``MAX_TRAY_NOTIFICATIONS`` notificaciones no leídas
        del ámbito solicitado, tras recortar las más antiguas si exceden el límite.
    """
    today = today or date.today()
    candidates = [c for c in _candidates(user, today) if c["scope"] == scope]
    _notify_missing(user, candidates)

    unread_qs = Notification.objects.filter(
        user=user, scope=scope, read=False
    ).order_by("-created_at")
    unread_ids = list(unread_qs.values_list("pk", flat=True))
    if len(unread_ids) > MAX_TRAY_NOTIFICATIONS:
        to_archive = unread_ids[MAX_TRAY_NOTIFICATIONS:]
        Notification.objects.filter(pk__in=to_archive).update(read=True)

    return list(
        Notification.objects.filter(
            user=user, scope=scope, read=False
        ).order_by("-created_at")[:MAX_TRAY_NOTIFICATIONS]
    )


# ---------------------------------------------------------------------------
# Web Push (VAPID): entrega externa de las alertas nuevas
# ---------------------------------------------------------------------------


def local_now(user) -> datetime:
    """``datetime`` consciente en la zona horaria del usuario (IANA).

    Si ``timezone_name`` no es una zona válida, cae a America/Caracas (la
    mayoría de la base de usuarios).
    """
    return datetime.now(_user_zone(user))


def _user_zone(user) -> ZoneInfo:
    """Zona horaria IANA del usuario con respaldo a America/Caracas."""
    name = getattr(user, "timezone_name", "") or _FALLBACK_TZ
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo(_FALLBACK_TZ)


def nudge_candidate(user, now_local: datetime) -> list[dict]:
    """Recordatorio diario «¿gastos sin registrar?».

    Reglas: solo DESPUÉS de ``NUDGE_LOCAL_HOUR`` hora local, y solo si el
    usuario NO registró ninguna transacción hoy (fecha local). La dedup por
    ``extra={"date": ...}`` lo limita a uno por día sin estado extra.
    """
    if now_local.hour < settings.NUDGE_LOCAL_HOUR:
        return []
    today_local = now_local.date()
    day_start_utc = datetime.combine(
        today_local, dt_time.min, tzinfo=now_local.tzinfo
    ).astimezone(dt_timezone.utc)
    if Transaction.objects.filter(
        user=user, created_at__gte=day_start_utc
    ).exists():
        return []
    return [
        {
            "kind": "expense_nudge",
            "scope": "personal",
            "extra": {"date": today_local.isoformat()},
            "title": "¿Gastos sin registrar?",
            "message": "Haz realizado algún gasto que deba registrar? Anótalo en NaviCash.",
        }
    ]


def send_web_push(subscription: PushSubscription, payload: dict) -> bool:
    """Envía un push cifrado a una suscripción. True si el servicio lo aceptó.

    Sin claves VAPID configuradas no intenta nada (modo degradado: las
    notificaciones siguen existiendo in-app). Ante 404/410 la suscripción
    quedó huérfana (usuario desinstaló/bloqueó) y se da de baja sola.
    """
    if not settings.VAPID_PUBLIC_KEY or not settings.VAPID_PRIVATE_KEY:
        return False
    try:
        webpush(
            subscription_info={
                "endpoint": subscription.endpoint,
                "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
            },
            data=json.dumps(payload),
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            vapid_claims={"sub": settings.VAPID_SUBJECT},
        )
    except WebPushException as exc:
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
        if status_code in (404, 410):
            subscription.delete()
            logger.warning(
                "push_subscription_gone endpoint_tail=%s status=%s",
                subscription.endpoint[-24:],
                status_code,
            )
        else:
            logger.warning("push_failed status=%s", status_code)
        return False
    except (ValueError, TypeError):
        # Claves VAPID malformadas o payload no serializable: no reintentar.
        logger.warning("push_invalid_config")
        return False
    subscription.last_success_at = dj_timezone.now()
    subscription.save(update_fields=["last_success_at"])
    return True


def deliver_pushes(user, items: list[Notification]) -> int:
    """Empuja las notificaciones nuevas a todos los dispositivos del usuario.

    Returns:
        Cantidad de envíos aceptados (notificación × dispositivo).
    """
    subs = list(PushSubscription.objects.filter(user=user))
    sent = 0
    for item in items[: settings.PUSH_MAX_PER_TICK]:
        payload = {
            "title": item.title,
            "body": item.message,
            "kind": item.kind,
            "scope": item.scope,
            "url": "/business" if item.scope == "business" else "/",
        }
        for sub in subs:
            if send_web_push(sub, payload):
                sent += 1
    return sent


def tick(now: datetime | None = None) -> dict[str, int] | None:
    """Un ciclo completo: genera alertas nuevas y las empuja, usuario a usuario.

    Solo procesa usuarios activos CON suscripción push. Un lock en caché
    impide ciclos solapados (patrón optimista set-before-work igual que el
    purge diario de cuentas); devuelve ``None`` si ya hay un ciclo corriendo.

    Returns:
        ``{"users": N, "pushed": M}`` o None si el lock estaba tomado.
    """
    if cache.get(TICK_LOCK_KEY):
        return None
    cache.set(TICK_LOCK_KEY, 1, timeout=TICK_LOCK_TTL_SECONDS)
    try:
        moment = now or dj_timezone.now()
        if dj_timezone.is_naive(moment):
            moment = dj_timezone.make_aware(moment)
        users = (
            User.objects.filter(
                is_active=True,
                notifications_pushsubscription__isnull=False,
            )
            .distinct()
            .iterator()
        )
        total_users = 0
        total_pushed = 0
        for user in users:
            now_local = moment.astimezone(_user_zone(user))
            candidates = _candidates(user, now_local.date()) + nudge_candidate(
                user, now_local
            )
            created = _notify_missing(user, candidates)
            total_users += 1
            if created:
                total_pushed += deliver_pushes(user, created)
        return {"users": total_users, "pushed": total_pushed}
    finally:
        cache.delete(TICK_LOCK_KEY)