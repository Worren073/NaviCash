"""checklists — Listas de compras del mercado.

- ``ShoppingList``: lista con productos (precio por unidad × cantidad).
- Al completarla se elige la cuenta de pago y el total real; el egreso se
  registra como operación ``tipo="pago"`` y descuenta la cuenta de inmediato.
"""

from rest_framework.routers import DefaultRouter

from apps.checklists.views import ShoppingListViewSet

router = DefaultRouter(trailing_slash=False)
router.register("checklists", ShoppingListViewSet, basename="checklist")

urlpatterns = router.urls