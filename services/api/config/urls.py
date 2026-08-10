"""Árbol de rutas raíz de la API de NaviCash.

Todas las rutas de la API cuelgan de ``/api/`` y cada app registra sus propias
rutas (definidas en su ``urls.py`` correspondiente).
"""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    # API de NaviCash (/api/auth, /api/rates, /api/wallets, ...)
    path("api/", include("apps.accounts.urls")),
    path("api/", include("apps.rates.urls")),
    path("api/", include("apps.wallets.urls")),
    path("api/", include("apps.transactions.urls")),
    path("api/", include("apps.savings.urls")),
    path("api/", include("apps.shortcuts.urls")),
    path("api/", include("apps.overview.urls")),
    path("api/", include("apps.notifications.urls")),
    path("api/", include("apps.subscriptions.urls")),
    path("api/", include("apps.assistant.urls")),
]

# ---------------------------------------------------------------------------
# Admin restringido (AUDIT M3)
# ---------------------------------------------------------------------------
# El panel /admin/ SOLO se registra en desarrollo (DEBUG=True). En
# producción no se expone por defecto: la estrategia definitiva (allowlist
# por red/IP o 2FA + proxy) se implementará por separado; lo importante es
# que una build de producción no publique /admin/ sin protección.
if settings.DEBUG:
    urlpatterns.insert(0, path("admin/", admin.site.urls))