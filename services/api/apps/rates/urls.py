"""rates — Tratamiento de tasas de cambio del dólar (DolarApi).

Responsabilidades:
1. Consultar la tasa oficial (BCV) del USD en Venezuela vía DolarApi.
2. Cachear la última tasa en la tabla ``ExchangeRate`` (TTL configurable).
3. Fallback robusto (R3): si la API falla, se sirve la última tasa con la
   marca ``is_stale=True``; y hay tasa manual de emergencia.
4. Endpoint público autenticado ``GET /api/rates/current`` y comando
   ``refresh_rates`` (usado por el cron de Render).

El proveedor está desacoplado tras una interfaz (``RateProvider``) para poder
cambiar de fuente sin tocar el resto del código (mitigación del Riesgo R3).
"""

from apps.rates.views import CurrentEuroRateView, CurrentRateView  # noqa: F401
from django.urls import path

urlpatterns = [
    path("rates/current", CurrentRateView.as_view(), name="rates-current"),
    path("rates/euro", CurrentEuroRateView.as_view(), name="rates-euro"),
]