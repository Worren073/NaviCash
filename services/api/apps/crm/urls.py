"""urls — Rutas del CRM del negocio."""

from __future__ import annotations

from rest_framework.routers import DefaultRouter

from apps.crm.views import (
    BusinessContactViewSet,
    CollectionFollowUpViewSet,
    InvoiceViewSet,
    OrderViewSet,
    ProductCategoryViewSet,
    ProductViewSet,
)

router = DefaultRouter()
router.register("contacts", BusinessContactViewSet, basename="business-contact")
router.register("invoices", InvoiceViewSet, basename="business-invoice")
router.register("orders", OrderViewSet, basename="business-order")
router.register("follow-ups", CollectionFollowUpViewSet, basename="business-follow-up")
router.register("products", ProductViewSet, basename="business-product")
router.register(
    "product-categories", ProductCategoryViewSet, basename="business-product-category"
)

urlpatterns = router.urls
