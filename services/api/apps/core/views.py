"""views — utilidades transversales de la API (salud y disponibilidad del servicio)."""

from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
    throttle_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@api_view(["GET"])
@authentication_classes([])
@throttle_classes([])
@permission_classes([AllowAny])
def health(request):  # noqa: ANN001 - firma exigida por DRF
    """Sonda de salud (liveness) para el keep-alive externo y el diagnóstico del borde.

    Sin autenticación, sin throttle y sin tocar la base de datos: responde 200
    aunque Postgres/Redis estén despertando. Sirve para mantener despierto el
    servicio free de Render y para responder "¿está viva la API?" sin consumir
    el presupuesto de rate-limit (que sí gastan login/registro).
    """
    return Response({"status": "ok"})


@api_view(["GET"])
@authentication_classes([])
@throttle_classes([])
@permission_classes([AllowAny])
def ready(request):  # noqa: ANN001
    """Sonda de preparación (readiness) para Render / K8s / balanceador.

    Verifica conectividad activa con PostgreSQL y con la caché (Redis).
    Devuelve 200 OK si ambos servicios están operativos, o 503 Service Unavailable
    si la base de datos o la caché no responden.
    """
    from django.core.cache import cache
    from django.db import connection

    checks: dict[str, str] = {"database": "ok", "cache": "ok"}
    is_ready = True

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1;")
            cursor.fetchone()
    except Exception as exc:  # noqa: BLE001
        checks["database"] = f"error: {exc}"
        is_ready = False

    try:
        cache.set("_readiness_probe", "1", timeout=5)
        if cache.get("_readiness_probe") != "1":
            checks["cache"] = "error: unable to read back key"
            is_ready = False
    except Exception as exc:  # noqa: BLE001
        checks["cache"] = f"error: {exc}"
        is_ready = False

    http_status = status.HTTP_200_OK if is_ready else status.HTTP_503_SERVICE_UNAVAILABLE
    return Response(
        {"status": "ready" if is_ready else "degraded", **checks},
        status=http_status,
    )
