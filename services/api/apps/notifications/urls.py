"""notifications — Alertas y Web Push.

- ``Notification``: alerta con categoría, texto y estado leída/no leída.
- Las notificaciones se regeneran al consultar (no son eventos en cola).
- ``PushSubscription`` + tick interno para la entrega Web Push.
"""

from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.notifications.views import (
    InternalTickView,
    NotificationViewSet,
    PushSubscriptionView,
    VapidPublicKeyView,
)

router = DefaultRouter(trailing_slash=False)
router.register("notifications", NotificationViewSet, basename="notification")

urlpatterns = router.urls + [
    path("push/vapid-key", VapidPublicKeyView.as_view()),
    path("push/subscriptions", PushSubscriptionView.as_view()),
    path("internal/tick", InternalTickView.as_view()),
]