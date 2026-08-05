"""serializers — Serializadores de ``rates``."""

from __future__ import annotations

from rest_framework import serializers

from apps.rates.models import ExchangeRate


class ExchangeRateSerializer(serializers.ModelSerializer):
    """Serializador público de una tasa de cambio.

    Devuelve ``rate`` como el ``effective_rate`` (promedio/venta/compra) y
    ``is_stale`` + ``updated_at`` para que la UI avise si la tasa está vieja.
    """

    rate = serializers.SerializerMethodField()

    class Meta:
        model = ExchangeRate
        fields = ["source", "currency", "compra", "venta", "rate", "is_stale", "rate_date", "input_at"]

    def get_rate(self, obj: ExchangeRate):
        """Expone la tasa efectiva para conversión (Decimal)."""
        return obj.effective_rate