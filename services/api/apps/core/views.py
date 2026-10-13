"""views — utilidades transversales de la API (salud del servicio)."""

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
    """Sonda de salud para el keep-alive externo y el diagnóstico del borde.

    Sin autenticación, sin throttle y sin tocar la base de datos: responde 200
    aunque Postgres/Redis estén despertando. Sirve para mantener despierto el
    servicio free de Render y para responder "¿está viva la API?" sin consumir
    el presupuesto de rate-limit (que sí gastan login/registro).
    """
    return Response({"status": "ok"})
