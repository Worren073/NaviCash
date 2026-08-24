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


class PushSubscriptionSerializer(serializers.Serializer):
    """Entrada de POST /api/push/subscriptions (formato estándar PushManager).

    ``endpoint``, ``keys.p256dh`` y ``keys.auth`` salen directamente del
    ``PushSubscription.toJSON()`` del navegador.
    """

    endpoint = serializers.URLField(max_length=500)
    keys = serializers.DictField(child=serializers.CharField())
    user_agent = serializers.CharField(
        required=False, allow_blank=True, max_length=200
    )

    def validate_keys(self, value: dict) -> dict:
        missing = {"p256dh", "auth"} - set(value)
        if missing:
            raise serializers.ValidationError(
                f"Faltan claves de cifrado: {', '.join(sorted(missing))}."
            )
        for name in ("p256dh", "auth"):
            if len(value[name]) > 120:
                raise serializers.ValidationError(f"{name} excede la longitud máxima.")
        return {k: v for k, v in value.items() if k in ("p256dh", "auth")}
