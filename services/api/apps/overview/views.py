"""views — Endpoints del resumen de home.

- ``GET /api/overview``: resumen del día y saldos consolidados.
- ``GET /api/overview/categories?kind=pay``: agregado por categoría.
"""

from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from apps.overview.serializers import OverviewSerializer
from apps.overview.services import aggregate_by_category, build_summary
from rest_framework.response import Response


class OverviewView(generics.GenericAPIView):
    """Devuelve el resumen consolidado de la home del usuario autenticado."""

    serializer_class = OverviewSerializer
    permission_classes = [IsAuthenticated]

    def get(self, request) -> Response:
        """GET /api/overview -> resumen de saldos, pendientes y próximos."""
        summary = build_summary(request.user)
        serializer = self.get_serializer(summary)
        return Response(serializer.data)


class CategoryBreakdownView(generics.GenericAPIView):
    """Devuelve operaciones agrupadas por categoría para gráficos.

    Query param:
        kind (str): "cobro" o "pago" (obligatorio).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request) -> Response:
        """GET /api/overview/categories?kind=<tipo> -> [{category, total}]."""
        kind = request.query_params.get("kind", "pago")
        if kind not in ("cobro", "pago"):
            return Response({"detail": "kind debe ser 'cobro' o 'pago'."}, status=400)
        data = aggregate_by_category(request.user, kind)
        return Response(data)