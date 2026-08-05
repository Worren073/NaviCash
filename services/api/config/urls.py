"""Árbol de rutas raíz de la API de NaviCash.

Todas las rutas de la API cuelgan de ``/api/`` y cada app registra sus propias
rutas (definidas en su ``urls.py`` correspondiente).
"""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    # API de NaviCash (/api/auth, /api/rates, /api/wallets, ...)
    path("api/", include("apps.accounts.urls")),
    path("api/", include("apps.rates.urls")),
    path("api/", include("apps.wallets.urls")),
    path("api/", include("apps.transactions.urls")),
    path("api/", include("apps.savings.urls")),
    path("api/", include("apps.shortcuts.urls")),
    path("api/", include("apps.overview.urls")),
]