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
    """Lectura del negocio: identidad + sus DOS cuentas (principal y secundaria).

    ``wallet_id``/``saldo`` se mantienen por compatibilidad y apuntan a la cuenta
    principal; ``accounts`` expone el detalle de ambas cuentas.
    """

    wallet_id = serializers.SerializerMethodField()
    saldo = serializers.SerializerMethodField()
    accounts = serializers.SerializerMethodField()

    class Meta:
        model = Business
        fields = ["id", "name", "currency", "wallet_id", "saldo", "accounts", "created_at"]
        read_only_fields = ["id", "created_at"]

    def get_wallet_id(self, obj: Business) -> str | None:
        """Id de la cuenta principal (o ``None`` si aún no existe)."""
        wallet = obj.wallet
        return str(wallet.pk) if wallet else None

    def get_saldo(self, obj: Business) -> str:
        """Saldo de la cuenta principal (en la moneda base del negocio)."""
        wallet = obj.wallet
        return str(wallet.saldo) if wallet else "0.00"

    def get_accounts(self, obj: Business) -> list[dict]:
        """Detalle de las cuentas del negocio (principal y secundaria)."""
        return [
            {
                "id": str(w.pk),
                "name": w.name,
                "currency": w.currency,
                "role": w.role,
                "balance": str(w.saldo),
            }
            for w in obj.wallets.all()
        ]