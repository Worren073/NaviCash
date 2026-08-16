"""serializers — Serializadores de ``wallets``."""

from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from apps.core.currency import is_valid_amount
from apps.wallets.models import Wallet
from apps.transactions.models import TRANSFER_RATE_SOURCES


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


class AdjustBalanceSerializer(serializers.Serializer):
    """Valida el cuerpo de ``POST /api/wallets/<id>/adjust``.

    Acepta exactamente uno de:
        delta: variación del saldo (positivo suma, negativo resta).
        new_balance: saldo final deseado de la billetera.

    Rechaza valores no finitos (NaN/Infinity) y cantidades con más de 2
    decimales o de magnitud desmedida, con 400 en vez de un 500.
    """

    delta = serializers.DecimalField(
        max_digits=20, decimal_places=2, required=False, write_only=True
    )
    new_balance = serializers.DecimalField(
        max_digits=20, decimal_places=2, required=False, write_only=True
    )

    def validate(self, attrs: dict) -> dict:
        """Debe venir al menos uno de los dos campos."""
        if "delta" not in attrs and "new_balance" not in attrs:
            raise serializers.ValidationError("Debes enviar 'delta' o 'new_balance' numérico.")
        return attrs


class TransferSerializer(serializers.Serializer):
    """Valida el cuerpo de ``POST /api/wallets/transfer``.

    Campos:
        source: id de la billetera origen.
        target: id de la billetera destino.
        amount: monto en la moneda de ``source``.
        rate_source: ``"oficial"`` (BCV) o ``"manual"``.
        custom_rate: tasa manual requerida si ``rate_source == "manual"``.
    """

    source = serializers.UUIDField()
    target = serializers.UUIDField()
    amount = serializers.DecimalField(max_digits=20, decimal_places=2)
    rate_source = serializers.ChoiceField(
        choices=[c[0] for c in TRANSFER_RATE_SOURCES], default="manual"
    )
    custom_rate = serializers.DecimalField(
        max_digits=20, decimal_places=4, required=False, allow_null=True
    )

    def __init__(self, *args, **kwargs):
        """Acota las billeteras al usuario autenticado (owner-scoped)."""
        super().__init__(*args, **kwargs)
        user = self.context["request"].user
        self._wallets = {w.id: w for w in Wallet.objects.filter(user=user).all()}

    def resolve_wallet(self, value) -> Wallet:
        """Devuelve la billetera del usuario o 400 si no existe."""
        wallet = self._wallets.get(value)
        if wallet is None:
            raise serializers.ValidationError("Billetera no válida.")
        return wallet

    def validate_amount(self, value):
        """El monto debe ser una cantidad positiva válida."""
        if not is_valid_amount(value):
            raise serializers.ValidationError("El monto debe ser mayor a 0.01.")
        return value

    def validate(self, attrs: dict) -> dict:
        """Valida coherencia entre origen, destino y tasa."""
        if attrs["source"] == attrs["target"]:
            raise serializers.ValidationError("No puedes transferir a la misma cuenta.")

        attrs["source_wallet"] = self.resolve_wallet(attrs.pop("source"))
        attrs["target_wallet"] = self.resolve_wallet(attrs.pop("target"))

        # Si ambas billeteras usan la misma moneda no hay conversión ni tasa.
        if attrs["source_wallet"].currency == attrs["target_wallet"].currency:
            attrs.pop("custom_rate", None)
            return attrs

        if attrs["rate_source"] == "oficial":
            attrs.pop("custom_rate", None)
        elif not attrs.get("custom_rate") or attrs["custom_rate"] <= 0:
            raise serializers.ValidationError(
                {"custom_rate": "Debes indicar una tasa personalizada mayor a cero."}
            )

        return attrs