"""notifications — Alertas generadas a partir del estado del dominio.

- ``Notification``: alerta con categoría, texto y estado leída/no leída.
- Las notificaciones se regeneran al consultar (no son eventos en cola).
"""

from rest_framework.routers import DefaultRouter

from apps.notifications.views import NotificationViewSet

router = DefaultRouter(trailing_slash=False)
router.register("notifications", NotificationViewSet, basename="notification")

urlpatterns = router.urls