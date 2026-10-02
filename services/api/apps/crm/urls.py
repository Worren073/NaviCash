"""urls — Rutas del CRM del negocio."""

from __future__ import annotations

from rest_framework.routers import DefaultRouter

from apps.crm.views import BusinessContactViewSet

router = DefaultRouter()
router.register("contacts", BusinessContactViewSet, basename="business-contact")

urlpatterns = router.urls
