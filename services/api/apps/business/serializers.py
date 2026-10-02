"""serializers — Serializadores del módulo Business."""

from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from apps.business.models import Business


class BusinessCreateSerializer(serializers.ModelSerializer):
    """Crea el negocio (solo escritura; la lectura usa ``BusinessSerializer``).

    - ``initial_capital``: capital EXTERNO aportado al nacer la cuenta
      (>= 0, dos decimales). Se acredita vía ``adjust_balance``.
    """

    initial_capital = serializers.DecimalField(
        max_digits=20,
        decimal_places=2,
        write_only=True,
        required=False,
        min_value=Decimal("0.00"),
        default=Decimal("0.00"),
    )

    class Meta:
        model = Business
        fields = ["name", "currency", "initial_capital"]

    def validate_name(self, value: str) -> str:
        """El nombre no puede quedar vacío ni solo espacios."""
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("El nombre del negocio no puede estar vacío.")
        return value


class BusinessSerializer(serializers.ModelSerializer):
    """Lectura del negocio: identidad + cuenta (billetera)."""

    wallet_id = serializers.SerializerMethodField()
    saldo = serializers.SerializerMethodField()

    class Meta:
        model = Business
        fields = ["id", "name", "currency", "wallet_id", "saldo", "created_at"]
        read_only_fields = ["id", "created_at"]

    def get_wallet_id(self, obj: Business) -> str:
        """UUID de la billetera del negocio (para filtrar sus operaciones)."""
        return str(obj.wallet.pk)

    def get_saldo(self, obj: Business) -> str:
        """Saldo actual de la cuenta del negocio (materializado en la wallet)."""
        return str(obj.wallet.saldo)