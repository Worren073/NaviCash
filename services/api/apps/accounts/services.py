"""services — Lógica de cuentas: eliminación con período de gracia y purga.

Flujo del "derecho de eliminación" (RGPD art. 17 / políticas de las tiendas):

1. ``POST /api/auth/delete-account`` verifica la contraseña y agenda la
   purga en ``User.deletion_scheduled_at`` (hoy + ``ACCOUNT_DELETION_GRACE_DAYS``
   días). Durante la gracia el usuario puede iniciar sesión y cancelar.
2. Al vencer la fecha, la cuenta y TODOS sus datos se borran (cascade +
   ``BalanceAuditLog``, cuya FK es SET_NULL, se elimina a mano).
3. La purga corre por dos vías: el comando ``purge_deleted_users`` (cron
   manual/externo) y un disparador perezoso diario desde ``MeView.get``,
   protegido con lock de caché para que cueste una vez al día por instancia.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from apps.accounts.models import User
from apps.wallets.models import BalanceAuditLog

logger = logging.getLogger(__name__)

#: Lock diario del disparador perezoso (valor: fecha ISO del último run).
PURGE_LOCK_KEY = "accounts:purge:last-run"

#: Corridas máximas por invocación del purge (lotes defensivos).
PURGE_MAX_BATCH = 500


def schedule_account_deletion(user: User) -> User:
    """Agenda la purga de la cuenta al finalizar el período de gracia.

    Idempotente: si ya había una fecha, se reprograma desde ahora (el usuario
    acaba de confirmar de nuevo con su contraseña).
    """
    user.deletion_scheduled_at = timezone.now() + timedelta(
        days=settings.ACCOUNT_DELETION_GRACE_DAYS
    )
    user.save(update_fields=["deletion_scheduled_at"])
    logger.info(
        "ACCOUNT_DELETION_SCHEDULED user=%s at=%s",
        user.pk,
        user.deletion_scheduled_at.isoformat(),
    )
    return user


def cancel_account_deletion(user: User) -> User:
    """Cancela una eliminación pendiente (vuelve la cuenta a estado normal)."""
    user.deletion_scheduled_at = None
    user.save(update_fields=["deletion_scheduled_at"])
    logger.info("ACCOUNT_DELETION_CANCELLED user=%s", user.pk)
    return user


def purge_due_accounts(now=None, exclude_user_pk: int | None = None) -> int:
    """Borra definitivamente las cuentas cuyo período de gracia ya venció.

    El ``user.delete()`` dispara el CASCADE de todas las FK (wallets,
    transacciones, metas, suscripciones, chats, notificaciones, tokens…).
    ``BalanceAuditLog.user`` es SET_NULL, así que esas filas se eliminan antes,
    explícitamente, para no dejar rastros huérfanos.

    Args:
        now: momento de referencia (tests); default ``timezone.now``.
        exclude_user_pk: usuario a conservar aunque su gracia esté vencida
            (disparador perezoso: no purgar al usuario del request en curso).

    Returns:
        Cantidad de usuarios eliminados.
    """
    now = now or timezone.now()
    due = User.objects.filter(deletion_scheduled_at__lte=now)
    if exclude_user_pk is not None:
        due = due.exclude(pk=exclude_user_pk)
    due_ids = list(due.values_list("pk", flat=True)[:PURGE_MAX_BATCH])
    if not due_ids:
        return 0

    BalanceAuditLog.objects.filter(user_id__in=due_ids).delete()
    # ``delete()`` devuelve (filas totales con cascadas, desglose por modelo);
    # nos interesa informar cuántos USUARIOS se eliminaron.
    total_rows, deletions = User.objects.filter(pk__in=due_ids).delete()
    deleted_users = deletions.get("accounts.User", 0)
    logger.warning(
        "ACCOUNTS_PURGED users=%s total_rows=%s ids=%s",
        deleted_users,
        total_rows,
        due_ids,
    )
    return deleted_users


def maybe_purge_daily(exclude_user_pk: int | None = None) -> int | None:
    """Disparador perezoso: ejecuta ``purge_due_accounts`` máximo 1 vez/día.

    Args:
        exclude_user_pk: usuario que dispara la comprobación; se excluye de la
            corrida para no eliminarlo en medio de su propio request (si su
            gracia ya venció lo purgará cualquier corrida posterior).

    Returns:
        Usuarios eliminados en esta corrida, o ``None`` si ya corrió hoy.
    """
    today = timezone.localdate().isoformat()
    if cache.get(PURGE_LOCK_KEY) == today:
        return None
    # Lock "optimista": se marca ANTES de purgar para que dos requests
    # simultáneos no dupliquen la corrida (peor caso: una corrida fallida
    # salta al día siguiente — el comando manual cubre ese hueco).
    cache.set(PURGE_LOCK_KEY, today, timeout=60 * 60 * 48)
    return purge_due_accounts(exclude_user_pk=exclude_user_pk)
