"""serializers — Serializador de ``notifications``."""

from __future__ import annotations

from rest_framework import serializers

from apps.notifications.models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    """Serializador de lectura de una notificación."""

    class Meta:
        model = Notification
        fields = ["id", "kind", "title", "message", "extra", "read", "created_at"]
        read_only_fields = ["id", "created_at"]
