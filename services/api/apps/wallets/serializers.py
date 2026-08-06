"""serializers — Serializadores de ``wallets``."""

from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from apps.wallets.models import Wallet


class WalletSerializer(serializers.ModelSerializer):
    """Serializador de billetera (lectura/escritura).

    - ``saldo_inicial`` es de solo escritura: al crearla define el saldo.
    - ``saldo`` es de solo lectura para el cliente (se modifica vía los
      servicios de transacciones o la acción ``adjust``).
    """

    saldo_inicial = serializers.DecimalField(
        max_digits=20,
        decimal_places=2,
        write_only=True,
        required=False,
        initial=Decimal("0.00"),
    )
    saldo = serializers.DecimalField(max_digits=20, decimal_places=2, read_only=True)

    class Meta:
        model = Wallet
        fields = ["id", "name", "currency", "tipo", "color", "saldo", "saldo_inicial", "created_at"]
        read_only_fields = ["id", "created_at"]

    def create(self, validated_data: dict) -> Wallet:
        """Crea la billetera con el saldo inicial provisto (o 0)."""
        initial = validated_data.pop("saldo_inicial", Decimal("0.00"))
        validated_data["user_id"] = self.context["request"].user.id
        wallet = Wallet.objects.create(**validated_data, saldo=initial)
        return wallet