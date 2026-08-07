"""views — ViewSet de billeteras con ajuste manual de saldo.

Endpoints:
- GET/POST  /api/wallets
- GET/PUT/PATCH/DELETE /api/wallets/<id>
- POST /api/wallets/<id>/adjust   (ajuste manual del saldo, ADR-08)
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.exceptions import BusinessRuleError
from apps.core.permissions import IsOwner
from apps.transactions.serializers import TransactionReadSerializer
from apps.transactions.services import create_transfer
from apps.wallets.models import Wallet
from apps.wallets.serializers import TransferSerializer, WalletSerializer
from apps.wallets.services import adjust_balance


class WalletViewSet(viewsets.ModelViewSet):
    """CRUD de billeteras del usuario autenticado.

    Solo se opera sobre las billeteras del propio usuario (filtrado por
    ``request.user`` en el queryset y permiso ``IsOwner`` en objetos).
    """

    serializer_class = WalletSerializer
    permission_classes = [IsOwner]

    def get_queryset(self):
        """Devuelve únicamente las billeteras del usuario autenticado."""
        return Wallet.objects.filter(user=self.request.user)

    @action(detail=True, methods=["post"])
    def adjust(self, request, pk=None):
        """Ajusta manualmente el saldo de la billetera (ADR-08).

        Body: ``{"delta": "10.00"}`` (positivo suma, negativo resta) o
        ``{"new_balance": "500.00"}`` para fijar directamente el saldo.
        """
        wallet = self.get_object()
        try:
            if "new_balance" in request.data:
                new_balance = Decimal(str(request.data["new_balance"]))
                delta = new_balance - wallet.saldo
            else:
                delta = Decimal(str(request.data["delta"]))
        except (InvalidOperation, KeyError, TypeError) as exc:
            raise BusinessRuleError("Debes enviar 'delta' o 'new_balance' numérico.") from exc

        try:
            new_saldo = adjust_balance(wallet, delta, reason="ajuste_manual")
        except ValueError as exc:
            raise BusinessRuleError(str(exc)) from exc

        return Response(
            {"detail": "Saldo ajustado.", "saldo": str(new_saldo)},
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["post"])
    def transfer(self, request):
        """Transfiere dinero entre dos billeteras del usuario.

        Body: ``{"source": id, "target": id, "amount": "100.00",
        "rate_source": "oficial|manual", "custom_rate": "860.00"}``.
        Devuelve la operación de transferencia creada.
        """
        serializer = TransferSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            tx = create_transfer(
                data["source_wallet"],
                data["target_wallet"],
                data["amount"],
                rate_fuente=data["rate_source"],
                custom_rate=data.get("custom_rate"),
            )
        except ValueError as exc:
            raise BusinessRuleError(str(exc)) from exc

        return Response(
            {"detail": "Transferencia registrada.", "transfer": TransactionReadSerializer(tx).data},
            status=status.HTTP_201_CREATED,
        )