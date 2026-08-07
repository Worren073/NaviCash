"""serializers — Serializador de ``subscriptions``.

Expone los campos de la mensualidad junto con los derivados de lectura
(progreso, días transcurridos y estado) calculados por el modelo.
"""

from __future__ import annotations

from rest_framework import serializers

from apps.core.currency import is_valid_amount
from apps.subscriptions.models import Subscription
from apps.wallets.models import Wallet


class SubscriptionSerializer(serializers.ModelSerializer):
    """Lectura/escritura de una mensualidad con sus derivados."""

    progress_percent = serializers.DecimalField(max_digits=6, decimal_places=1, read_only=True)
    days_total = serializers.IntegerField(read_only=True)
    days_elapsed = serializers.IntegerField(read_only=True)
    days_remaining = serializers.IntegerField(read_only=True)
    status = serializers.CharField(read_only=True)
    can_renew = serializers.BooleanField(read_only=True)

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
            "days_remaining",
            "status",
            "can_renew",
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


class SubscriptionRenewSerializer(serializers.Serializer):
    """Registro de una renovación: cuenta de gasto y monto.

    El monto debe ser > 0 y la cuenta debe pertenecer al usuario. La fecha de
    renovación se fija al `hoy` y el período se extiende la misma duración del
    anterior.
    """

    wallet = serializers.PrimaryKeyRelatedField(queryset=Wallet.objects.none())
    amount = serializers.DecimalField(max_digits=20, decimal_places=2)

    def __init__(self, *args, **kwargs):
        """Acota las cuentas al usuario de la request."""
        super().__init__(*args, **kwargs)
        user = self.context["request"].user
        self.fields["wallet"].queryset = Wallet.objects.filter(user=user).all()

    def validate_amount(self, value):
        """El gasto debe ser una cantidad válida (>= 0.01)."""
        if not is_valid_amount(value):
            raise serializers.ValidationError("El monto del gasto debe ser mayor a 0.01.")
        return value