"""middleware — Eventos de seguridad 401/403 estructurados para SIEM.

Registra cada respuesta 401 (No autenticado) y 403 (Prohibido) con
metadata relevante: IP del cliente, endpoint, método HTTP, y user-agent.
Nunca se loguean payloads ni datos sensibles del usuario.
"""

from __future__ import annotations

import logging

from django.utils.deprecation import MiddlewareMixin

sec_logger = logging.getLogger("apps.accounts.security")


class SecurityEventMiddleware(MiddlewareMixin):
    """Log de respuestas 401/403 para detección de anomalías."""

    def process_response(self, request, response):
        if response.status_code in (401, 403):
            level = "WARNING" if response.status_code == 403 else "INFO"
            sec_logger.log(
                getattr(logging, level),
                "PERMISSION_DENIED status=%s method=%s path=%s ip=%s ua=%s",
                response.status_code,
                request.method,
                request.path,
                request.META.get("REMOTE_ADDR", "?"),
                request.META.get("HTTP_USER_AGENT", "?")[:200],
            )
        return response
