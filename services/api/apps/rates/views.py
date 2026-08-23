"""views — Endpoints de ``rates``."""

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.rates.providers import RateProviderError
from apps.rates.serializers import ExchangeRateSerializer
from apps.rates.service import get_current_euro_rate, get_current_official_rate


class CurrentRateView(APIView):
    """Devuelve la tasa oficial (BCV) actual del dólar.

    GET /api/rates/current -> ``{source, currency, compra, venta, rate,
    is_stale, rate_date, input_at}``.

    Si la API está caída y no hay caché responde 503 con mensaje claro
    (la UI muestra "tasa no disponible" en ese caso).
    """

    def get(self, request):
        try:
            rate = get_current_official_rate(stale_ok=True)
        except RateProviderError:
            return Response(
                {"detail": "No se pudo obtener la tasa del día.", "code": "rate_unavailable"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(ExchangeRateSerializer(rate).data)


class CurrentEuroRateView(APIView):
    """Devuelve la tasa oficial (BCV) actual del euro.

    GET /api/rates/euro -> ``{source, currency, compra, venta, rate,
    is_stale, rate_date, input_at}``.
    """

    def get(self, request):
        try:
            rate = get_current_euro_rate(stale_ok=True)
        except RateProviderError:
            return Response(
                {"detail": "No se pudo obtener la tasa del euro del día.", "code": "rate_unavailable"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(ExchangeRateSerializer(rate).data)