"""Overview — Resumen consolidado del home dashboard.

Endpoints:
- ``GET /api/overview``: resumen del día y saldos (RF-22 a RF-26 del PLAN).
- ``GET /api/overview/categories?kind=pay``: agregado por categoría.

No usa modelo propio; agrega los dominios existentes (wallets, transactions,
rates) y serializa a JSON en ``views``.
"""

from django.urls import path

from apps.overview.views import CategoryBreakdownView, OverviewView

urlpatterns = [
    path("overview", OverviewView.as_view(), name="overview-summary"),
    path("overview/categories", CategoryBreakdownView.as_view(), name="overview-categories"),
]