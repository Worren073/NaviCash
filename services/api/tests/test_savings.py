"""tests — Metas de ahorro y aportes (conversión congelada)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.db import IntegrityError, connection
from django.db.models.deletion import ProtectedError

from apps.rates.models import ExchangeRate
from apps.savings.models import GoalContribution, SavingsGoal
from factories import GoalContributionFactory, SavingsGoalFactory, WalletFactory


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

    def test_contributions_list_paginated(self, api_client) -> None:
        """GET /savings/<id>/contributions pagina con el paginador global (M4)."""
        goal = SavingsGoalFactory(user=api_client.user, target_amount=Decimal("100000.00"))
        for _ in range(30):
            GoalContributionFactory(
                user=api_client.user,
                goal=goal,
                amount=Decimal("1.00"),
                amount_goal_currency=Decimal("1.00"),
            )
        resp = api_client.get(f"/api/savings/{goal.id}/contributions")
        assert resp.status_code == 200
        assert resp.data["count"] == 30
        assert len(resp.data["results"]) == 25
        assert resp.data["next"] is not None
        assert resp.data["previous"] is None

        resp2 = api_client.get(f"/api/savings/{goal.id}/contributions?page=2")
        assert len(resp2.data["results"]) == 5
        assert resp2.data["previous"] is not None

    def test_list_goals_bounded_queries(self, api_client, django_assert_num_queries, monkeypatch) -> None:
        """El listado de metas NO hace N+1 (A8): 5 queries fijas.

        Sin el ``prefetch_related`` y la suma en Python, cada meta añadiría una
        query por aportes más otra por cuentas afiliadas.
        """
        monkeypatch.setattr("apps.savings.models.get_current_official_rate", lambda: None)
        goal = SavingsGoalFactory(user=api_client.user, target_amount=Decimal("1000.00"))
        for _ in range(3):
            GoalContributionFactory(
                user=api_client.user,
                goal=goal,
                amount=Decimal("10.00"),
                amount_goal_currency=Decimal("10.00"),
            )
        account = WalletFactory(user=api_client.user, tipo="saving", saldo=Decimal("50.00"))
        goal.linked_accounts.add(account)

        with django_assert_num_queries(5):
            resp = api_client.get("/api/savings")
        assert resp.status_code == 200
        assert resp.data["count"] == 1
        assert resp.data["results"][0]["contributions_count"] == 3
        assert resp.data["results"][0]["total_contributed"] == "80.00"


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
class TestGoalDelete:
    """C4: las metas con aportes no pueden borrarse (PROTECT amable)."""

    URL = "/api/savings"

    def test_goal_with_contributions_cannot_be_deleted(self, api_client) -> None:
        """Borrar una meta con aportes responde 400 con mensaje claro."""
        goal = SavingsGoalFactory(user=api_client.user, target_amount=Decimal("1000.00"))
        GoalContributionFactory(user=api_client.user, goal=goal)
        resp = api_client.delete(f"{self.URL}/{goal.id}")
        assert resp.status_code == 400
        assert "aportes" in resp.data["detail"]
        # La meta sigue visible y su historial intacto.
        listing = api_client.get(self.URL)
        assert listing.data["count"] == 1

    def test_goal_without_contributions_can_be_deleted(self, api_client) -> None:
        """Una meta sin aportes sí puede borrarse (204 y desaparece)."""
        goal = SavingsGoalFactory(user=api_client.user)
        resp = api_client.delete(f"{self.URL}/{goal.id}")
        assert resp.status_code == 204
        listing = api_client.get(self.URL)
        assert listing.data["count"] == 0

    def test_db_protects_goal_with_contributions(self, api_client) -> None:
        """A nivel de motor, PROTECT bloquea el borrado en cascada."""
        goal = SavingsGoalFactory(user=api_client.user)
        GoalContributionFactory(user=api_client.user, goal=goal)
        with pytest.raises(ProtectedError):
            SavingsGoal.objects.filter(pk=goal.pk).delete()


@pytest.mark.django_db
class TestCheckConstraints:
    """A10: el motor rechaza aportes no positivos (salta validación de API)."""

    def _supported(self) -> None:
        if not connection.features.supports_table_check_constraints:
            pytest.skip(
                "El motor no soporta CheckConstraints; la constraint solo se "
                "aplica en motores que las ejecutan."
            )

    def test_zero_amount_rejected_by_db(self, api_client) -> None:
        """Un aporte de 0 lanza IntegrityError en el motor."""
        self._supported()
        goal = SavingsGoalFactory(user=api_client.user)
        with pytest.raises(IntegrityError):
            GoalContribution.objects.create(
                user=api_client.user,
                goal=goal,
                amount=Decimal("0.00"),
                currency="USD",
            )

    def test_negative_amount_rejected_by_db(self, api_client) -> None:
        """Un aporte negativo lanza IntegrityError en el motor."""
        self._supported()
        goal = SavingsGoalFactory(user=api_client.user)
        with pytest.raises(IntegrityError):
            GoalContribution.objects.create(
                user=api_client.user,
                goal=goal,
                amount=Decimal("-1.00"),
                currency="USD",
            )


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