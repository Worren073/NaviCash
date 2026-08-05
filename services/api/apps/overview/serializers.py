"""serializers — Serializadores del resumen de home.

Convierten el dict plano de ``overview.services.build_summary`` a una respuesta
JSON tipada. Nota: estas clases son "serializadores de lectura pura": no usan
modelo ni validación de entrada.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from rest_framework import serializers


class WalletSummarySerializer(serializers.Serializer):
    """Serializador de solo lectura de una billetera en el resumen."""

    id = serializers.UUIDField()
    name = serializers.CharField()
    currency = serializers.CharField()
    saldo = serializers.DecimalField(max_digits=20, decimal_places=2)
    usd_value = serializers.DecimalField(
        max_digits=20, decimal_places=2, allow_null=True, required=False
    )


class TransactionBriefSerializer(serializers.Serializer):
    """Serializador resumido de una operación próxima a vencer."""

    id = serializers.UUIDField()
    tipo = serializers.CharField()
    concepto = serializers.CharField()
    monto = serializers.DecimalField(max_digits=20, decimal_places=2)
    moneda = serializers.CharField()
    fecha_vencimiento = serializers.DateField()
    contact_name = serializers.SerializerMethodField()

    def get_contact_name(self, obj) -> str | None:
        """Nombre del contacto (si existe) para mostrar en la lista."""
        contact = getattr(obj, "contact", None)
        return contact.name if contact else None


class OverviewSerializer(serializers.Serializer):
    """Resumen agregado de la home (solo lectura)."""

    base_currency = serializers.CharField()
    rate = serializers.DecimalField(
        max_digits=20, decimal_places=4, allow_null=True, required=False
    )
    total_balance_usd = serializers.DecimalField(max_digits=20, decimal_places=2)
    to_receive = serializers.DecimalField(max_digits=20, decimal_places=2)
    to_pay = serializers.DecimalField(max_digits=20, decimal_places=2)
    overdue = serializers.DecimalField(max_digits=20, decimal_places=2)
    wallets = WalletSummarySerializer(many=True)
    upcoming = TransactionBriefSerializer(many=True)

    def to_representation(self, instance: dict) -> dict[str, Any]:
        """Prepara el dict plano para JSON (ya viene agregado el rate como Decimal)."""
        return super().to_representation(instance)