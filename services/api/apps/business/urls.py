"""business — Módulo de negocio del usuario.

Registra los endpoints del negocio (perfil/creación, resumen del dashboard y
analíticas financieras) colgando de ``/api/business``. La billetera del negocio
se crea aquí y se aísla del mundo personal en los scopes de wallets,
transacciones y overview.
"""

from django.urls import path

from apps.business.views import (
    BusinessAnalyticsView,
    BusinessSummaryView,
    BusinessView,
)

urlpatterns = [
    path("business", BusinessView.as_view(), name="business-profile"),
    path("business/summary", BusinessSummaryView.as_view(), name="business-summary"),
    path("business/analytics", BusinessAnalyticsView.as_view(), name="business-analytics"),
]