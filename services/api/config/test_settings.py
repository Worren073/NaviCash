"""Settings para tests: heredan de ``settings`` y fuerzan entorno aislado.

- SQLite en memoria (rápido, sin depender de Postgres en CI/dev local).
- Proveedor de tasas estático (RATE_PROVIDER=static -> StaticRateProvider),
  así los tests no llaman a DolarApi ni dependen de la red.
- Email a console (se puede inspeccionar con django.core.mail.outbox).
- AUTH_PASSWORD_VALIDATORS vacío para facilitar la creación de usuarios.
"""

from .settings import *  # noqa: F401,F403

# ---------------------------------------------------------------------------
# Sobre-escribimos solo lo necesario para un entorno de prueba hermético.
# ---------------------------------------------------------------------------

# Base de datos en memoria (se crea por test).
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# Proveedor de tasas: estático, sin llamadas a la red.
RATE_PROVIDER = "static"

# TTL corto para pruebas de caché/fallback de tasas.
RATE_TTL_MINUTES = 60

# Email a la "bandeja de salida" en memoria (testea outbox[0]).
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Relajamos las validaciones de contraseña: los tests crean usuarios directos
# (factory-boy) y no necesitan contraseñas "fuertes".
AUTH_PASSWORD_VALIDATORS = []

# Sin tasa de referencia ni dependencias de terceros en tests.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "navicash-tests",
    }
}

# DEBUG=True permite que RegisterView devuelva ``debug_token``.
DEBUG = True

SECRET_KEY = "tests-secret-key"  # noqa: S105

# Cookie de auth no requiere HTTPS en tests.
SIMPLE_JWT = {
    **SIMPLE_JWT,
    "AUTH_COOKIE_SECURE": False,
}