"""Throttling con diagnóstico.

Un 429 puede nacer en tres sitios: el throttle de DRF (scope), el lockout por
cuenta o el borde de la infraestructura (Cloudflare/Render). El handler global
de excepciones siempre devuelve un cuerpo legible, así que cuando un 429 llega
sin ``detail`` no procede de aquí: estas clases dejan la traza necesaria para
demostrarlo (clave exacta que usa DRF, que en prod sale de X-Forwarded-For).
"""

from __future__ import annotations

import logging

from rest_framework.throttling import ScopedRateThrottle

sec_logger = logging.getLogger("apps.accounts.security")


class LoggedScopedRateThrottle(ScopedRateThrottle):
    """``ScopedRateThrottle`` que registra cada corte para poder atribuirlo.

    No modifica la tasa ni la clave: solo emite ``THROTTLED`` con el scope, la
    identidad usada por DRF, el X-Forwarded-For completo y la REMOTE_ADDR.
    """

    def allow_request(self, request, view) -> bool:  # noqa: ANN001
        allowed = super().allow_request(request, view)
        if not allowed:
            sec_logger.warning(
                "THROTTLED scope=%s ident=%s xff=%s ip=%s",
                getattr(view, "throttle_scope", "-") or "-",
                self.get_ident(request),
                request.META.get("HTTP_X_FORWARDED_FOR") or "-",
                request.META.get("REMOTE_ADDR", "?"),
            )
        return allowed
