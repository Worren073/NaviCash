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


@pytest.mark.django_db
class TestGoalLinkedAccounts:
    """Afiliación de cuentas de ahorro a una meta."""

    URL = "/api/savings"

    def test_create_with_linked_account(self, api_client) -> None:
        """Al crear con una cuenta de ahorro, la meta la afilia."""
        account = WalletFactory(user=api_client.user, tipo="saving", saldo=Decimal("250.00"))
        resp = api_client.post(
            self.URL,
            {
                "name": "Emergencias",
                "target_amount": "1000.00",
                "linked_account_ids": [str(account.id)],
            },
        )
        assert resp.status_code == 201
        assert str(resp.data["linked_accounts"][0]["id"]) == str(account.id)
        # El progreso incluye el saldo de la cuenta afiliada.
        assert resp.data["total_contributed"] == "250.00"

    def test_inherits_currency_from_account(self, api_client) -> None:
        """La meta hereda la moneda de su primera cuenta afiliada."""
        account = WalletFactory(user=api_client.user, tipo="saving", currency="VES")
        resp = api_client.post(
            self.URL,
            {
                "name": "Ahorro en Bs",
                "target_amount": "100000.00",
                "linked_account_ids": [str(account.id)],
            },
        )
        assert resp.status_code == 201
        assert resp.data["currency"] == "VES"

    def test_explicit_currency_wins(self, api_client) -> None:
        """Si se envía moneda explícita, se respeta sobre la de la cuenta."""
        account = WalletFactory(user=api_client.user, tipo="saving", currency="VES")
        resp = api_client.post(
            self.URL,
            {
                "name": "Meta",
                "target_amount": "1000.00",
                "currency": "USD",
                "linked_account_ids": [str(account.id)],
            },
        )
        assert resp.status_code == 201
        assert resp.data["currency"] == "USD"

    def test_progress_sums_multiple_accounts(self, api_client) -> None:
        """Con dos cuentas, el progreso es la suma de ambos saldos."""
        a1 = WalletFactory(user=api_client.user, tipo="saving", saldo=Decimal("100.00"))
        a2 = WalletFactory(user=api_client.user, tipo="saving", saldo=Decimal("150.00"))
        goal = SavingsGoalFactory(user=api_client.user, target_amount=Decimal("1000.00"))
        resp = api_client.patch(
            f"{self.URL}/{goal.id}",
            {"linked_account_ids": [str(a1.id), str(a2.id)]},
            format="json",
        )
        assert resp.status_code == 200
        assert resp.data["total_contributed"] == "250.00"

    def test_only_saving_wallets_allowed(self, api_client) -> None:
        """Solo billeteras de tipo ahorro pueden afiliarse."""
        cash = WalletFactory(user=api_client.user, tipo="cash")
        goal = SavingsGoalFactory(user=api_client.user)
        resp = api_client.patch(
            f"{self.URL}/{goal.id}", {"linked_account_ids": [str(cash.id)]}, format="json"
        )
        assert resp.status_code == 400

    def test_cannot_link_other_users_wallet(self, api_client) -> None:
        """Las cuentas de otro usuario no pueden vincularse."""
        foreign = WalletFactory(tipo="saving")
        goal = SavingsGoalFactory(user=api_client.user)
        resp = api_client.patch(
            f"{self.URL}/{goal.id}", {"linked_account_ids": [str(foreign.id)]}, format="json"
        )
        assert resp.status_code == 400

    def test_unlink_accounts(self, api_client) -> None:
        """Quitar cuentas deja el progreso solo con aportes manuales."""
        account = WalletFactory(user=api_client.user, tipo="saving", saldo=Decimal("200.00"))
        goal = SavingsGoalFactory(user=api_client.user)
        goal.linked_accounts.set([account])
        assert goal.total_contributed == Decimal("200.00")
        resp = api_client.patch(f"{self.URL}/{goal.id}", {"linked_account_ids": []}, format="json")
        assert resp.status_code == 200
        assert resp.data["total_contributed"] == "0.00"

    def test_ves_account_converted_to_usd_goal(self, api_client) -> None:
        """Cuenta VES en meta USD se convierte con la tasa del día."""
        from django.utils import timezone

        ExchangeRate.objects.create(
            source="oficial",
            currency="VES",
            promedio=Decimal("100.00"),
            rate_date=timezone.now(),
        )
        account = WalletFactory(
            user=api_client.user, tipo="saving", currency="VES", saldo=Decimal("10000.00")
        )
        goal = SavingsGoalFactory(user=api_client.user, currency="USD")
        resp = api_client.patch(
            f"{self.URL}/{goal.id}", {"linked_account_ids": [str(account.id)]}, format="json"
        )
        assert resp.status_code == 200
        assert resp.data["total_contributed"] == "100.00"