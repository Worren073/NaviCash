"""serializers — Serializador de atajos."""

from rest_framework import serializers

from apps.shortcuts.models import Shortcut


class ShortcutSerializer(serializers.ModelSerializer):
    """Serializador CRUD de atajos del home."""

    class Meta:
        model = Shortcut
        fields = ["id", "label", "kind", "config", "order", "icon"]
        read_only_fields = ["id"]

    def create(self, validated_data: dict) -> Shortcut:
        """Crea el atajo ligado al usuario autenticado."""
        validated_data["user_id"] = self.context["request"].user.id
        return super().create(validated_data)