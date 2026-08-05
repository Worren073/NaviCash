"""transactions — Cobros y pagos (núcleo de NaviCash).

- ``Transaction``: operación de cobro (ingreso) o pago (egreso) con estados
  pendiente / pagado / cancelado y transición automática a "retrasado" cuando
  vence y sigue pendiente (calculado al consultar, Riesgo R8).
- ``Category``: categorías predefinidas + propias del usuario.
- ``Contact``: personas/entidades recurrentes para autocompletar.

La conversión a USD se CONGELA al registrar (R2/R4): cada transacción guarda
``monto_usd``, ``tasa_usd`` y ``fuente_tasa`` del momento.
"""

from apps.transactions.views import (  # noqa: F401
    CategoryViewSet,
    ContactViewSet,
    TransactionViewSet,
)
from rest_framework.routers import DefaultRouter

router = DefaultRouter(trailing_slash=False)
router.register("transactions", TransactionViewSet, basename="transaction")
router.register("categories", CategoryViewSet, basename="category")
router.register("contacts", ContactViewSet, basename="contact")

urlpatterns = router.urls