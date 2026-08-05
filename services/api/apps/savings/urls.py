"""savings — Metas de ahorro y aportes.

- ``SavingsGoal``: meta con monto objetivo, moneda y fecha objetivo opcional.
- ``GoalContribution``: cada aporte (con su billetera de origen opcional).

El progreso se calcula como suma de aportes (``total_contributed``) y el
porcentaje de avance se expone en el serializer.
"""

from apps.savings.views import GoalViewSet  # noqa: F401
from rest_framework.routers import DefaultRouter

router = DefaultRouter(trailing_slash=False)
router.register("savings", GoalViewSet, basename="savings-goal")

urlpatterns = router.urls