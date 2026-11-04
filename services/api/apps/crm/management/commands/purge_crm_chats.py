"""purge_crm_chats — Retención y purga de conversaciones, mensajes y adjuntos de CRM.

Uso:
    python manage.py purge_crm_chats [--days 180] [--dry-run] [--attachments-only]

Elimina mensajes de chat y libera adjuntos binarios en el almacenamiento
(S3 / Cloudflare R2 o disco local) con más de ``--days`` de antigüedad (default 180).

Opciones:
    --days N              Días de retención (default: 180).
    --dry-run             Simula la purga sin borrar registros ni archivos.
    --attachments-only    Solo elimina los binarios pesados conservando el texto del chat.
"""

from __future__ import annotations

from datetime import timedelta
import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.crm.models import ChatAttachment, ChatConversation, ChatMessage

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Comando Django para purga programada de mensajes y adjuntos antiguos."""

    help = "Purga mensajes y adjuntos de chat antiguos de CRM conforme a la política de retención."

    def add_arguments(self, parser) -> None:
        """Argumentos de configuración de retención."""
        parser.add_argument(
            "--days",
            type=int,
            default=180,
            help="Antigüedad mínima en días para purgar (default: 180).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Modo simulación: reporta qué se eliminaría sin ejecutar cambios.",
        )
        parser.add_argument(
            "--attachments-only",
            action="store_true",
            help="Solo elimina los archivos binarios de almacenamiento (R2/S3), conservando mensajes.",
        )

    def handle(self, *args, **options) -> None:
        days: int = options["days"]
        dry_run: bool = options["dry_run"]
        attachments_only: bool = options["attachments_only"]

        cutoff = timezone.now() - timedelta(days=days)
        prefix = "[DRY-RUN] " if dry_run else ""

        self.stdout.write(
            f"{prefix}Iniciando purga de chats con fecha de corte: {cutoff.isoformat()} ({days} días)."
        )

        old_attachments = ChatAttachment.objects.filter(created_at__lt=cutoff)
        att_count = old_attachments.count()

        files_deleted = 0
        if not dry_run:
            for att in old_attachments.iterator(chunk_size=200):
                if att.file:
                    try:
                        att.file.delete(save=False)
                        files_deleted += 1
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(
                            "Error al eliminar archivo adjunto %s: %s", att.id, exc
                        )
            if attachments_only:
                old_attachments.update(file="")
        else:
            files_deleted = att_count

        self.stdout.write(
            f"{prefix}Adjuntos procesados para eliminación de binarios: {files_deleted}"
        )

        if attachments_only:
            self.stdout.write(
                self.style.SUCCESS(
                    f"{prefix}Purga de adjuntos finalizada. Los mensajes se conservaron."
                )
            )
            return

        old_messages = ChatMessage.objects.filter(created_at__lt=cutoff)
        msg_count = old_messages.count()

        if not dry_run:
            old_messages.delete()

        self.stdout.write(f"{prefix}Mensajes de chat eliminados: {msg_count}")

        # Purga de conversaciones vacías creadas antes de la fecha de corte
        empty_conversations = ChatConversation.objects.filter(
            created_at__lt=cutoff, messages__isnull=True
        )
        empty_count = empty_conversations.count()

        if not dry_run:
            empty_conversations.delete()

        self.stdout.write(
            f"{prefix}Conversaciones inactivas vacías eliminadas: {empty_count}"
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}Purga de chats completada con éxito. "
                f"Mensajes: {msg_count}, Adjuntos: {files_deleted}, Conversaciones: {empty_count}."
            )
        )
