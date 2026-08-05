"""wallets — Billeteras y saldos.

Representa las "cuentas" de dinero del usuario (Efectivo Bs, Efectivo USD,
Banco X, ...). El saldo se actualiza automáticamente cuando una operación se
marca como pagada (ADR-08: cobro suma, pago resta) y admite además un ajuste
manual para corregir diferencias o movimientos fuera de la app.
"""

from apps.wallets.views import WalletViewSet  # noqa: F401
from rest_framework.routers import DefaultRouter

router = DefaultRouter(trailing_slash=False)
router.register("wallets", WalletViewSet, basename="wallet")

urlpatterns = router.urls