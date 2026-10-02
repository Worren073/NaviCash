"""business — Módulo de negocio del usuario.

Registra los endpoints del negocio (perfil/creación y resumen del dashboard)
colgando de ``/api/business``. La billetera del negocio se crea aquí y se
aísla del mundo personal en los scopes de wallets, transacciones y overview.
"""

from django.urls import path

from apps.business.views import BusinessSummaryView, BusinessView

urlpatterns = [
    path("business", BusinessView.as_view(), name="business-profile"),
    path("business/summary", BusinessSummaryView.as_view(), name="business-summary"),
]