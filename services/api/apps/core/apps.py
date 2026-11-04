"""Configuración de la app ``core``."""

from django.apps import AppConfig
from django.core.checks import Error, Tags, register


@register(Tags.security)
def check_field_encryption_key(app_configs, **kwargs):  # noqa: ANN001
    """Verifica que FIELD_ENCRYPTION_KEY esté configurada en entornos de producción."""
    from django.conf import settings

    errors = []
    if not getattr(settings, "DEBUG", True):
        key = getattr(settings, "FIELD_ENCRYPTION_KEY", "") or ""
        if not str(key).strip():
            errors.append(
                Error(
                    "FIELD_ENCRYPTION_KEY no está configurada en producción.",
                    hint=(
                        "Genera una clave con: python -c "
                        "'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
                    ),
                    id="core.E001",
                )
            )
    return errors


class CoreConfig(AppConfig):
    """AppConfig de ``core``: utilidades transversales del dominio."""

    name = "apps.core"
    verbose_name = "Núcleo"
