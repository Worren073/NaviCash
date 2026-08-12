"""Configuración principal de Django para NaviCash.

El módulo lee los valores desde variables de entorno (vía ``django-environ``)
para funcionar igual en el contenedor (host = ``db``) que en producción
(Render). En desarrollo (DEBUG=True) funcionan los valores del entorno local
(ver ``infra/docker-compose.yml``); en producción (DEBUG=False) aplica
fail-fast: si faltan secretos o se usan los valores de desarrollo conocidos,
el arranque falla con ``ImproperlyConfigured`` (AUDIT A2).
"""

import sys
from datetime import timedelta
from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured

# ---------------------------------------------------------------------------
# Rutas base
# ---------------------------------------------------------------------------
# BASE_DIR = services/api (raíz del proyecto Django).
BASE_DIR = Path(__file__).resolve().parent.parent

# Instancia de environ para leer variables del entorno.
env = environ.Env(
    # Valores por defecto para entornos que no definan la variable.
    # DEBUG sin default engañoso: ausente/vacío significa producción (False),
    # nunca asumir True. Los secretos no tienen default de desarrollo: si
    # faltan en producción, el fail-fast de abajo detiene el arranque.
    DEBUG=(bool, False),
    DJANGO_SECRET_KEY=(str, ""),
    DJANGO_ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1", "api"]),
    CORS_ALLOWED_ORIGINS=(list, ["http://localhost:5173"]),
    DJANGO_DB_ENGINE=(str, "django.db.backends.postgresql"),
    POSTGRES_DB=(str, "navicash"),
    POSTGRES_USER=(str, "navicash"),
    POSTGRES_PASSWORD=(str, ""),
    POSTGRES_HOST=(str, "localhost"),
    POSTGRES_PORT=(str, "5432"),
    # sslmode de la conexión PG: "prefer" en dev sin SSL; producción define
    # DJANGO_DB_SSLMODE (p. ej. "require") desde su entorno (AUDIT M7).
    DJANGO_DB_SSLMODE=(str, "prefer"),
    # URL de la caché compartida (Redis). El default es SOLO dev: en
    # producción el fail-fast de abajo exige un valor real (AUDIT C2).
    REDIS_URL=(str, "redis://redis:6379/0"),
    DJANGO_EMAIL_BACKEND=(str, "django.core.mail.backends.console.EmailBackend"),
    DJANGO_EMAIL_HOST=(str, ""),
    DJANGO_EMAIL_PORT=(int, 587),
    DJANGO_EMAIL_HOST_USER=(str, ""),
    DJANGO_EMAIL_HOST_PASSWORD=(str, ""),
    DJANGO_EMAIL_USE_TLS=(bool, True),
    DJANGO_EMAIL_USE_SSL=(bool, False),
    DEFAULT_FROM_EMAIL=(str, "NaviCash <navicashvnz@gmail.com>"),
    EMAIL_TIMEOUT=(int, 10),
    # Brevo (API HTTP, puerto 443): envío de correos en producción. El egress
    # SMTP (465/587) está bloqueado por red, por eso se usa la API HTTP.
    BREVO_API_KEY=(str, ""),
    BREVO_SENDER_EMAIL=(str, "navicashvnz@gmail.com"),
    BREVO_SENDER_NAME=(str, "NaviCash"),
    # Si False, los usuarios se crean activos sin requerir verificación de
    # email (temporal, hasta tener dominio para Resend).
    EMAIL_VERIFICATION_REQUIRED=(bool, True),
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
    # Habilitación global del CAPTCHA (True por defecto; ver sección CAPTCHA).
    CAPTCHA_ENABLED=(bool, True),
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
# Fail-fast de secretos (AUDIT A2): nada de valores de desarrollo en prod
# ---------------------------------------------------------------------------
# Valores conocidos del entorno de desarrollo (docker-compose local). Si la
# app arranca con DEBUG=False y alguno de los secretos falta o coincide con
# estos placeholders, NEGAMOS el arranque: es preferible fallar a correr en
# producción con contraseñas/claves públicas en los manuales del repo.
_DEV_SECRET_KEY = "dev-secret-key-cambiar-en-produccion"
_DEV_DB_PASSWORD = "navicash-dev-password"
_DEV_REDIS_URL = "redis://redis:6379/0"

if not DEBUG:
    if not SECRET_KEY or SECRET_KEY == _DEV_SECRET_KEY:
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY es obligatoria en producción (DEBUG=False) y no "
            "puede ser la clave de desarrollo. Genera una nueva, p. ej. con "
            "'python -c \"import secrets; print(secrets.token_urlsafe(64))\"'."
        )
    _db_password = env("POSTGRES_PASSWORD")
    if not _db_password or _db_password == _DEV_DB_PASSWORD:
        raise ImproperlyConfigured(
            "POSTGRES_PASSWORD es obligatoria en producción (DEBUG=False) y no "
            "puede ser la contraseña de desarrollo 'navicash-dev-password'."
        )
    # AUDIT C2/M7: sin Redis no hay caché compartida (throttle del asistente
    # por-worker y confirmaciones volatiles), y el default de dev apunta a un
    # host del compose local: en prod debe venir una REDIS_URL real (p. ej.
    # Redis managed en el proveedor, con TLS) o el arranque se niega.
    _redis_url = env("REDIS_URL")
    if not _redis_url or _redis_url == _DEV_REDIS_URL:
        raise ImproperlyConfigured(
            "REDIS_URL es obligatoria en producción (DEBUG=False): el default "
            "de desarrollo ('redis://redis:6379/0') no es válido fuera del "
            "compose local. Configura la URL de tu Redis gestionado."
        )

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
    "apps.assistant",
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
        # AUDIT M7: conexiones persistentes con health-check (no se entrega
        # una conexión muerta tras un restart del PG) y timeout de conexión
        # corto + sslmode explícito (default "prefer": el compose local no
        # tiene SSL; producción fuerza "require" por env).
        "CONN_MAX_AGE": 60,
        "CONN_HEALTH_CHECKS": True,
        "OPTIONS": {
            "connect_timeout": 5,
            "sslmode": env("DJANGO_DB_SSLMODE"),
        },
    }
}

# ---------------------------------------------------------------------------
# Caché compartida (Redis) — AUDIT C2
# ---------------------------------------------------------------------------
# Con gunicorn multi-worker la caché NO puede ser por-proceso: el throttle
# del asistente (30/h) y las transferencias pendientes de confirmación se
# guardan en un worker arbitrario y se perderían (o se ejecutarían dos veces)
# con LocMemCache. Redis es la caché default de producción; los tests usan
# LOCMEM (ver config/test_settings.py: CACHES se sobre-escribe ahí y NUNCA
# tocan redis).
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": env("REDIS_URL"),
        "TIMEOUT": 300,
        "OPTIONS": {
            "CONNECTION_POOL_KWARGS": {"socket_timeout": 3},
        },
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
    # Throttling global (AUDIT A1): anónimos por IP, autenticados por cuenta,
    # y scopes dedicados para auth frágil (login/register/verify) y el chat.
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ),
    # Rate limit dedicado para el chat del asistente (AUDIT A4: sin throttling).
    # El scope se declara en la vista (throttle_scope="assistant").
    "DEFAULT_THROTTLE_RATES": {
        "anon": "60/min",
        "user": "120/min",
        "login": "5/min",
        "register": "3/hour",
        "email_verify": "10/hour",
        "assistant": env("ASSISTANT_THROTTLE_RATE", default="30/hour"),
    },
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
# ``CAPTCHA_ENABLED`` es el interruptor global de verificación del CAPTCHA.
# En desarrollo puede quedar vacío (el bypass ``CAPTCHA_DEV_BYPASS`` omite la
# verificación), pero OJO: en producción (DEBUG=False) el secreto
# ``TURNSTILE_SECRET_KEY`` es OBLIGATORIO. La verificación es fail-closed
# (AUDIT A1): la lógica en ``apps/accounts/captcha.py`` debe rechazar el
# registro si no hay secreto configurado, nunca abrirse silenciosamente.
CAPTCHA_ENABLED = env("CAPTCHA_ENABLED")
TURNSTILE_SECRET_KEY = env("TURNSTILE_SECRET_KEY")
TURNSTILE_VERIFY_URL = env("TURNSTILE_VERIFY_URL")
CAPTCHA_DEV_BYPASS = env("CAPTCHA_DEV_BYPASS")
TERMS_VERSION = env("TERMS_VERSION")

# ---------------------------------------------------------------------------
# Hardening HTTPS/cookies (AUDIT A3): solo cuando DEBUG=False
# ---------------------------------------------------------------------------
# En producción la app va detrás de un proxy TLS (Render/PaaS): confiamos en
# el header X-Forwarded-Proto, redirigimos todo a HTTPS con HSTS de 1 año y
# marcamos las cookies de sesión/CSRF como Secure. En desarrollo (DEBUG=True)
# estos flags quedan apagados para permitir HTTP local.
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

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
EMAIL_USE_SSL = env("DJANGO_EMAIL_USE_SSL")
EMAIL_TIMEOUT = env("EMAIL_TIMEOUT")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL")
BREVO_API_KEY = env("BREVO_API_KEY")
BREVO_SENDER_EMAIL = env("BREVO_SENDER_EMAIL")
BREVO_SENDER_NAME = env("BREVO_SENDER_NAME")
EMAIL_VERIFICATION_REQUIRED = env("EMAIL_VERIFICATION_REQUIRED")

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

# ---------------------------------------------------------------------------
# Logging estructurado (AUDIT M2): todo a stdout (lo recoge el orquestador
# del contenedor), con timestamp/nivel/logger para filtrar por servicio.
# ---------------------------------------------------------------------------
# IMPORTANTE: el formatter solo incluye METADATA (tiempo, nivel, módulo,
# mensaje). Nunca se loguean payloads ni cuerpos de request/respuesta: los
# datos financieros del usuario NO deben aparecer en logs. Los llamados
# existentes a logger.warning / logger.exception siguen funcionando igual.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{asctime} {levelname} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "stream": sys.stdout,
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "DEBUG" if DEBUG else "INFO",
    },
    "loggers": {
        # Django general: INFO en ambos modos (no interesa el ruido DEBUG de
        # los frameworks en prod).
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        # Requests HTTP: en DEBUG los 4xx/5xx se ven (WARNING); en prod solo
        # los errores 5xx (ERROR). No se registra el body de la petición.
        "django.request": {
            "handlers": ["console"],
            "level": "DEBUG" if DEBUG else "ERROR",
            "propagate": False,
        },
        # Apps propias (asistant, rates, accounts, ...): a DEGUG en dev para
        # rastrear flujos; a INFO en prod para no saturar.
        "apps": {
            "handlers": ["console"],
            "level": "DEBUG" if DEBUG else "INFO",
            "propagate": False,
        },
    },
}