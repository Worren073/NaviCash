"""serializers — Serializadores de ``savings``.

Usamos ``GoalWriteSerializer`` (crear/editar meta), ``ContributionSerializer``
(crear aportes dentro de una meta) y ``GoalReadSerializer`` (detalle con
progreso calculado).
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from rest_framework import serializers

from apps.core.currency import CURRENCY_CHOICES, is_valid_amount
from apps.core.exceptions import BusinessRuleError
from apps.savings.models import GoalContribution, SavingsGoal
from apps.savings.services import add_contribution
from apps.wallets.models import Wallet


class GoalReadSerializer(serializers.ModelSerializer):
    """Serializador de lectura de una meta con su progreso calculado."""

    total_contributed = serializers.DecimalField(max_digits=20, decimal_places=2, read_only=True)
    progress_percent = serializers.DecimalField(max_digits=6, decimal_places=1, read_only=True)
    contributions_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = SavingsGoal
        fields = [
            "id",
            "name",
            "target_amount",
            "currency",
            "target_date",
            "total_contributed",
            "progress_percent",
            "contributions_count",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def get_contributions_count(self, obj):
        """Cuenta de aportes de la meta."""
        return obj.contributions.count()


class GoalWriteSerializer(serializers.ModelSerializer):
    """Serializador de alta/edición de metas."""

    class Meta:
        model = SavingsGoal
        fields = ["name", "target_amount", "currency", "target_date"]

    def create(self, validated_data: dict) -> SavingsGoal:
        """Crea la meta ligada al usuario autenticado."""
        validated_data["user_id"] = self.context["request"].user.id
        return super().create(validated_data)


class ContributionSerializer(serializers.Serializer):
    """Añade un aporte a una meta (ruta: POST /api/savings/<id>/contributions).

    Campos:
        amount: cantidad aportada.
        currency: moneda del aporte.
        wallet: billetera de origen (opcional).
        note: nota (opcional).
    """

    amount = serializers.DecimalField(max_digits=20, decimal_places=2)
    currency = serializers.ChoiceField(choices=CURRENCY_CHOICES)
    wallet = serializers.PrimaryKeyRelatedField(
        queryset=Wallet.objects.none(), required=False, allow_null=True
    )
    note = serializers.CharField(max_length=200, required=False, allow_blank=True)

    def __init__(self, *args, **kwargs):
        """Acota la queryset de billeteras al usuario de la request."""
        super().__init__(*args, **kwargs)
        user = self.context["request"].user
        self.fields["wallet"].queryset = Wallet.objects.filter(user=user).all()

    def validate_amount(self, value):
        """La cantidad debe ser un monto válido."""
        if not is_valid_amount(value):
            raise serializers.ValidationError("El aporte debe ser mayor a 0.01.")
        return value

    def create_contribution(self, goal: SavingsGoal, user) -> GoalContribution:
        """Delega en el servicio de negocio ``add_contribution``.

        Args:
            goal: meta a la que aportar.
            user: usuario autenticado.

        Returns:
            El aporte creado.
        """
        try:
            return add_contribution(
                goal,
                amount=self.validated_data["amount"],
                currency=self.validated_data["currency"],
                wallet=self.validated_data.get("wallet"),
                note=self.validated_data.get("note", ""),
                user=user,
            )
        except BusinessRuleError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc