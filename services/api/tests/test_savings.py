"""tests — Metas de ahorro y aportes (conversión congelada)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.rates.models import ExchangeRate
from apps.savings.models import GoalContribution, SavingsGoal
from factories import SavingsGoalFactory, WalletFactory


@pytest.mark.django_db
class TestGoalCreate:
    """POST /api/savings."""

    URL = "/api/savings"

    def test_creates_goal(self, api_client) -> None:
        """Crea una meta USD con su monto objetivo."""
        resp = api_client.post(
            self.URL,
            {"name": "Vacaciones", "target_amount": "1000.00", "currency": "USD"},
        )
        assert resp.status_code == 201
        assert resp.data["total_contributed"] == "0.00"

    def test_list_shows_progress(self, api_client) -> None:
        """El listado devuelve progreso y cuenta de aportes."""
        SavingsGoalFactory(user=api_client.user, target_amount=Decimal("1000.00"))
        resp = api_client.get(self.URL)
        assert resp.status_code == 200
        assert resp.data["count"] == 1
        assert resp.data["results"][0]["progress_percent"] == "0.0"


@pytest.mark.django_db
class TestContributions:
    """POST /api/savings/<id>/contributions."""

    def _contribute(self, api_client, goal, amount="100.00", currency="USD"):
        """Helper: registra un aporte."""
        return api_client.post(
            f"/api/savings/{goal.id}/contributions",
            {"amount": amount, "currency": currency},
        )

    def test_contribution_same_currency(self, api_client) -> None:
        """Aporte en la misma moneda: sin conversión."""
        goal = SavingsGoalFactory(user=api_client.user, target_amount=Decimal("1000.00"))
        resp = self._contribute(api_client, goal, amount="100.00")
        assert resp.status_code == 201
        goal.refresh_from_db()
        assert goal.total_contributed == Decimal("100.00")

    def test_contribution_usd_to_ves_goal(self, api_client) -> None:
        """Meta USD recibe aporte VES y congela la conversión con la tasa."""
        from django.utils import timezone

        ExchangeRate.objects.create(
            source="oficial",
            currency="VES",
            promedio=Decimal("100.00"),
            rate_date=timezone.now(),
        )
        goal = SavingsGoalFactory(user=api_client.user, currency="USD")
        resp = self._contribute(api_client, goal, amount="1000.00", currency="VES")
        assert resp.status_code == 201
        contribution = GoalContribution.objects.get(goal=goal)
        assert contribution.amount_goal_currency == Decimal("10.00")

    def test_contribution_updates_progress(self, api_client) -> None:
        """Dos aportes de 100 en meta de 1000 => 20% de progreso."""
        goal = SavingsGoalFactory(user=api_client.user, target_amount=Decimal("1000.00"))
        self._contribute(api_client, goal)
        self._contribute(api_client, goal)
        resp = api_client.get(f"/api/savings/{goal.id}")
        assert resp.data["total_contributed"] == "200.00"
        assert float(resp.data["progress_percent"]) == 20.0

    def test_contribution_with_wallet(self, api_client) -> None:
        """Un aporte puede indicar la billetera de origen."""
        wallet = WalletFactory(user=api_client.user, currency="USD")
        goal = SavingsGoalFactory(user=api_client.user)
        resp = api_client.post(
            f"/api/savings/{goal.id}/contributions",
            {"amount": "50.00", "currency": "USD", "wallet": str(wallet.id)},
        )
        assert resp.status_code == 201


@pytest.mark.django_db
class TestGoalOwnership:
    """Un usuario no puede aportar a metas ajenas."""

    def test_contribution_to_other_goal(self, auth_client_factory) -> None:
        """Aportar a la meta de otro usuario falla (404 por scoping)."""
        other_goal = SavingsGoalFactory()
        client = auth_client_factory()
        resp = client.post(
            f"/api/savings/{other_goal.id}/contributions",
            {"amount": "10.00", "currency": "USD"},
        )
        assert resp.status_code in (403, 404)

    def test_cannot_delete_other_goal(self, auth_client_factory) -> None:
        """Borrar la meta de otro usuario falla."""
        other_goal = SavingsGoalFactory()
        client = auth_client_factory()
        resp = client.delete(f"/api/savings/{other_goal.id}")
        assert resp.status_code in (403, 404)