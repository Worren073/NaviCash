"""subscriptions — Mensualidades con avance por tiempo.

- ``Subscription``: nombre, color y período (inicio → cierre).
- El progreso (%) se calcula por tiempo transcurrido del período.
"""

from rest_framework.routers import DefaultRouter

from apps.subscriptions.views import SubscriptionViewSet

router = DefaultRouter(trailing_slash=False)
router.register("subscriptions", SubscriptionViewSet, basename="subscription")

urlpatterns = router.urls