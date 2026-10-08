"""views — Endpoints del módulo Business.

- ``GET  /api/business``: perfil del negocio (200) o 404 si no existe.
- ``POST /api/business``: lo crea (201); 409 si ya existe.
- ``GET  /api/business/summary``: métricas del dashboard (404 sin negocio).
- ``GET  /api/business/analytics``: analíticas financieras del negocio.
"""

from __future__ import annotations

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.business.models import Business
from apps.business.serializers import BusinessCreateSerializer, BusinessSerializer
from apps.business.services import (
    build_business_analytics,
    build_business_summary,
    create_business,
)
from apps.transactions.serializers import TransactionReadSerializer


class BusinessView(APIView):
    """Perfil del negocio del usuario (fetch o creación en primer acceso)."""

    permission_classes = [IsAuthenticated]

    def _business(self, request):
        """Negocio del usuario con su billetera (o ``None``)."""
        return (
            Business.objects.filter(user=request.user).select_related("wallet").first()
        )

    def get(self, request) -> Response:
        """GET /api/business -> 200 con el negocio, 404 si no existe."""
        business = self._business(request)
        if business is None:
            return Response(
                {"detail": "No tienes un negocio creado."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(BusinessSerializer(business).data)

    def post(self, request) -> Response:
        """POST /api/business -> crea el negocio; 409 si ya existe uno."""
        if self._business(request) is not None:
            return Response(
                {"detail": "Ya tienes un negocio creado."},
                status=status.HTTP_409_CONFLICT,
            )
        serializer = BusinessCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        business = create_business(request.user, **serializer.validated_data)
        return Response(BusinessSerializer(business).data, status=status.HTTP_201_CREATED)


class BusinessSummaryView(APIView):
    """Métricas del dashboard de negocio (solo su cuenta, nunca lo personal)."""

    permission_classes = [IsAuthenticated]

    def get(self, request) -> Response:
        """GET /api/business/summary -> {saldo, ingresos/egresos del mes, recent}."""
        business = (
            Business.objects.filter(user=request.user).select_related("wallet").first()
        )
        if business is None:
            return Response(
                {"detail": "No tienes un negocio creado."},
                status=status.HTTP_404_NOT_FOUND,
            )
        summary = build_business_summary(business)
        recent = TransactionReadSerializer(summary.pop("recent"), many=True).data
        return Response({**summary, "recent": recent})


class BusinessAnalyticsView(APIView):
    """Analíticas del tablero financiero del negocio (solo su cuenta)."""

    permission_classes = [IsAuthenticated]

    def get(self, request) -> Response:
        """GET /api/business/analytics?months=6|12 -> tablero completo.

        ``months`` define la ventana de la serie P&L (admite 3-24; por defecto
        12). Si el usuario no tiene negocio devuelve 404.
        """
        business = (
            Business.objects.filter(user=request.user).select_related("wallet").first()
        )
        if business is None:
            return Response(
                {"detail": "No tienes un negocio creado."},
                status=status.HTTP_404_NOT_FOUND,
            )
        raw = request.query_params.get("months", "12")
        try:
            months = int(raw)
        except (TypeError, ValueError):
            months = 12
        months = max(3, min(24, months))
        return Response(build_business_analytics(business, months=months))