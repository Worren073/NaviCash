"""urls — Rutas del CRM del negocio."""

from __future__ import annotations

from rest_framework.routers import DefaultRouter

from apps.crm.views import BusinessContactViewSet, InvoiceViewSet

router = DefaultRouter()
router.register("contacts", BusinessContactViewSet, basename="business-contact")
router.register("invoices", InvoiceViewSet, basename="business-invoice")

urlpatterns = router.urls
