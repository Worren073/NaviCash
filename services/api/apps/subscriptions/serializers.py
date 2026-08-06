"""serializers — Serializador de ``subscriptions``.

Expone los campos de la mensualidad junto con los derivados de lectura
(progreso, días transcurridos y estado) calculados por el modelo.
"""

from __future__ import annotations

from rest_framework import serializers

from apps.subscriptions.models import Subscription


class SubscriptionSerializer(serializers.ModelSerializer):
    """Lectura/escritura de una mensualidad con sus derivados."""

    progress_percent = serializers.DecimalField(max_digits=6, decimal_places=1, read_only=True)
    days_total = serializers.IntegerField(read_only=True)
    days_elapsed = serializers.IntegerField(read_only=True)
    status = serializers.CharField(read_only=True)

    class Meta:
        model = Subscription
        fields = [
            "id",
            "name",
            "color",
            "start_date",
            "end_date",
            "progress_percent",
            "days_total",
            "days_elapsed",
            "status",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def validate(self, attrs: dict) -> dict:
        """El cierre debe ser posterior o igual al inicio."""
        start = attrs.get("start_date", getattr(self.instance, "start_date", None))
        end = attrs.get("end_date", getattr(self.instance, "end_date", None))
        if start and end and end < start:
            raise serializers.ValidationError(
                {"end_date": "La fecha de cierre debe ser posterior o igual a la de inicio."}
            )
        return attrs

    def create(self, validated_data: dict) -> Subscription:
        """Crea la mensualidad ligada al usuario autenticado."""
        validated_data["user_id"] = self.context["request"].user.id
        return super().create(validated_data)