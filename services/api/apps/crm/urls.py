"""urls — Rutas del CRM del negocio."""

from __future__ import annotations

from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.crm.views import (
    BusinessContactViewSet,
    ChatConversationViewSet,
    CollectionFollowUpViewSet,
    InstagramConfigView,
    InstagramOAuthCallbackView,
    InstagramOAuthStartView,
    InstagramWebhookView,
    InvoiceViewSet,
    OrderViewSet,
    ProductCategoryViewSet,
    ProductViewSet,
    WhatsAppConfigView,
    WhatsAppWebhookView,
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
router.register("chats", ChatConversationViewSet, basename="business-chat")

urlpatterns = [
    # Webhook público de Meta (sin JWT; autenticado por firma HMAC).
    path("whatsapp/webhook/", WhatsAppWebhookView.as_view(), name="whatsapp-webhook"),
    # Credenciales de WhatsApp del negocio autenticado.
    path("whatsapp/config/", WhatsAppConfigView.as_view(), name="whatsapp-config"),
    # Instagram Messaging (Instagram Login): OAuth + webhook + estado.
    path(
        "instagram/oauth/start/",
        InstagramOAuthStartView.as_view(),
        name="instagram-oauth-start",
    ),
    path(
        "instagram/oauth/callback/",
        InstagramOAuthCallbackView.as_view(),
        name="instagram-oauth-callback",
    ),
    path(
        "instagram/webhook/",
        InstagramWebhookView.as_view(),
        name="instagram-webhook",
    ),
    path(
        "instagram/config/",
        InstagramConfigView.as_view(),
        name="instagram-config",
    ),
    *router.urls,
]
