"""Configuración principal de Django para NaviCash.

El módulo lee los valores desde variables de entorno (vía ``django-environ``)
para funcionar igual en el contenedor (host = ``db``) que en producción
(Render). Por defecto funciona en modo DEBUG=1 (desarrollo).
"""

from datetime import timedelta
from pathlib import Path

import environ

# ---------------------------------------------------------------------------
# Rutas base
# ---------------------------------------------------------------------------
# BASE_DIR = services/api (raíz del proyecto Django).
BASE_DIR = Path(__file__).resolve().parent.parent

# Instancia de environ para leer variables del entorno.
env = environ.Env(
    # Valores por defecto para entornos que no definan la variable.
    DEBUG=(bool, True),
    DJANGO_SECRET_KEY=(str, "dev-secret-key-cambiar-en-produccion"),
    DJANGO_ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1", "api"]),
    CORS_ALLOWED_ORIGINS=(list, ["http://localhost:5173"]),
    DJANGO_DB_ENGINE=(str, "django.db.backends.postgresql"),
    POSTGRES_DB=(str, "navicash"),
    POSTGRES_USER=(str, "navicash"),
    POSTGRES_PASSWORD=(str, "navicash-dev-password"),
    POSTGRES_HOST=(str, "localhost"),
    POSTGRES_PORT=(str, "5432"),
    DJANGO_EMAIL_BACKEND=(str, "django.core.mail.backends.console.EmailBackend"),
    DJANGO_EMAIL_HOST=(str, ""),
    DJANGO_EMAIL_PORT=(int, 587),
    DJANGO_EMAIL_HOST_USER=(str, ""),
    DJANGO_EMAIL_HOST_PASSWORD=(str, ""),
    DJANGO_EMAIL_USE_TLS=(bool, True),
    JWT_ACCESS_MINUTES=(int, 15),
    JWT_REFRESH_DAYS=(int, 30),
    VERIFICATION_TOKEN_HOURS=(int, 24),
    RATE_TTL_MINUTES=(int, 60),
    # Proveedor de tasas activo: "dolarapi" (producción) o "static" (tests).
    RATE_PROVIDER=(str, "dolarapi"),
    APP_BASE_URL=(str, "http://localhost:5173"),
    # Cloudflare Turnstile (CAPTCHA del registro).
    TURNSTILE_SECRET_KEY=(str, ""),
    TURNSTILE_VERIFY_URL=(str, "https://challenges.cloudflare.com/turnstile/v0/siteverify"),
    # En desarrollo, sin clave configurada, la verificación se omite.
    CAPTCHA_DEV_BYPASS=(bool, True),
    # Versión vigente de los términos que se graba al aceptar.
    TERMS_VERSION=(str, "v1-2026-08"),
)

# ---------------------------------------------------------------------------
# Configuración básica
# ---------------------------------------------------------------------------
DEBUG = env("DEBUG")
SECRET_KEY = env("DJANGO_SECRET_KEY")
ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS")

# ---------------------------------------------------------------------------
# Aplicaciones instaladas
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Terceros
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    # Módulos propios (apps es un paquete; usamos ruta completa)
    "apps.accounts",
    "apps.core",
    "apps.rates",
    "apps.wallets",
    "apps.transactions",
    "apps.savings",
    "apps.shortcuts",
    "apps.overview",
    "apps.notifications",
    "apps.subscriptions",
]

MIDDLEWARE = [
    # CORS debe ir lo más arriba posible (antes de CommonMiddleware).
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ---------------------------------------------------------------------------
# Base de datos (PostgreSQL)
# ---------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": env("DJANGO_DB_ENGINE"),
        "NAME": env("POSTGRES_DB"),
        "USER": env("POSTGRES_USER"),
        "PASSWORD": env("POSTGRES_PASSWORD"),
        "HOST": env("POSTGRES_HOST"),
        "PORT": env("POSTGRES_PORT"),
    }
}

# ---------------------------------------------------------------------------
# Autenticación, contraseñas y usuario custom
# ---------------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"

# Argon2 como primer hasher (más resistente que PBKDF2 por defecto).
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# DRF y JWT
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        # Autenticación al API con JWT Bearer (token access de corta vida).
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        # Por defecto todo requiere usuario autenticado.
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.DefaultPagination",
    "PAGE_SIZE": 25,
    # Errores en el mismo formato/estilo espagnol-friendly.
    "EXCEPTION_HANDLER": "apps.core.exceptions.base_exception_handler",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env("JWT_ACCESS_MINUTES")),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env("JWT_REFRESH_DAYS")),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    # El refresh se manda/lee en una cookie httpOnly llamada "refresh_token".
    "AUTH_COOKIE": "refresh_token",
    "AUTH_COOKIE_HTTP_ONLY": True,
    "AUTH_COOKIE_SECURE": not DEBUG,
    "AUTH_COOKIE_SAMESITE": "Lax",
    "AUTH_COOKIE_PATH": "/api/auth/",
}

# ---------------------------------------------------------------------------
# CAPTCHA (Cloudflare Turnstile) y términos de servicio
# ---------------------------------------------------------------------------
TURNSTILE_SECRET_KEY = env("TURNSTILE_SECRET_KEY")
TURNSTILE_VERIFY_URL = env("TURNSTILE_VERIFY_URL")
CAPTCHA_DEV_BYPASS = env("CAPTCHA_DEV_BYPASS")
TERMS_VERSION = env("TERMS_VERSION")

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = env("CORS_ALLOWED_ORIGINS")
CORS_ALLOW_CREDENTIALS = True  # para que la cookie httpOnly pueda viajar.

# ---------------------------------------------------------------------------
# i18n / zona horaria
# ---------------------------------------------------------------------------
# Español latino por defecto. Las fechas se muestran en la zona del usuario
# y la BD almacena instantes UTC (USE_TZ=True).
LANGUAGE_CODE = "es-VE"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

LANGUAGES = [("es", "Español")]

# ---------------------------------------------------------------------------
# Email (consola en dev; SMTP configurable en prod)
# ---------------------------------------------------------------------------
EMAIL_BACKEND = env("DJANGO_EMAIL_BACKEND")
EMAIL_HOST = env("DJANGO_EMAIL_HOST")
EMAIL_PORT = env("DJANGO_EMAIL_PORT")
EMAIL_HOST_USER = env("DJANGO_EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = env("DJANGO_EMAIL_HOST_PASSWORD")
EMAIL_USE_TLS = env("DJANGO_EMAIL_USE_TLS")
DEFAULT_FROM_EMAIL = "NaviCash <no-reply@navicash.app>"

# ---------------------------------------------------------------------------
# Configuración de negocio (tasas, verificación)
# ---------------------------------------------------------------------------
# Proveedor de tasas activo ("dolarapi" o "static" en pruebas).
RATE_PROVIDER = env("RATE_PROVIDER")
# TTL de la caché de tasas (minutos).
RATE_TTL_MINUTES = env("RATE_TTL_MINUTES")
# Referencia para la conversión: todos los valores se normalizan a USD.
RATE_REFERENCE_CURRENCY = "USD"
# Caducidad de los tokens de verificación de email.
VERIFICATION_TOKEN_HOURS = env("VERIFICATION_TOKEN_HOURS")

# URL base de la SPA (se usa para construir enlaces de verificación).
APP_BASE_URL = env("APP_BASE_URL")

# ---------------------------------------------------------------------------
# Archivos estáticos
# ---------------------------------------------------------------------------
STATIC_URL = "static/"

# ---------------------------------------------------------------------------
# Varios
# ---------------------------------------------------------------------------
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"