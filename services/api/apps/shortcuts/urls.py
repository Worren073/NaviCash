"""shortcuts — Atajos del home (acciones frecuentes en uno o dos taps).

Un atajo referencia una acción predefinida (ej. "Cobrar a María $20" o
"Aportar a vacaciones") con su configuración en JSON. El frontend lo renderiza
como botón rápido; la app abre el formulario pre-rellenado.
"""

from apps.shortcuts.views import ShortcutViewSet  # noqa: F401
from rest_framework.routers import DefaultRouter

router = DefaultRouter(trailing_slash=False)
router.register("shortcuts", ShortcutViewSet, basename="shortcut")

urlpatterns = router.urls