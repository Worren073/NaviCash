#!/usr/bin/env python
"""Punto de entrada estándar de Django para el proyecto NaviCash.

Este script expone la funcionalidad de `django-admin` para el proyecto
(arrancar el servidor, ejecutar migraciones, comandos personalizados, tests,
etc.) usando la configuración de producción/desarrollo según el entorno.
"""

import os
import sys


def main() -> None:
    """Delega en django-admin apuntando al módulo de configuración del proyecto."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "No se pudo importar Django. ¿Está instalado y activo el entorno "
            "del contenedor? (pip install -r requirements.txt)"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()