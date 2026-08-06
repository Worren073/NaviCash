"""tests — Mensualidades: CRUD y progreso por tiempo del período."""

from __future__ import annotations

from datetime import date

import pytest
from rest_framework.test import APIClient

from apps.subscriptions.models import Subscription
from factories import UserFactory


def _payload(**overrides) -> dict:
    """Payload válido de una mensualidad."""
    payload = {
        "name": "Gimnasio",
        "color": "#10b981",
        "start_date": "2026-07-01",
        "end_date": "2026-09-30",
    }
    payload.update(overrides)
    return payload


@pytest.mark.django_db
class TestSubscriptions:
    """CRUD de mensualidades (GET/POST /api/subscriptions)."""

    URL = "/api/subscriptions"

    def test_create_subscription(self, api_client) -> None:
        """Crear una mensualidad devuelve 201 con los derivados."""
        resp = api_client.post(self.URL, _payload())
        assert resp.status_code == 201
        assert resp.data["name"] == "Gimnasio"
        assert resp.data["color"] == "#10b981"
        assert "progress_percent" in resp.data
        assert "status" in resp.data

    def test_end_before_start_rejected(self, api_client) -> None:
        """Cierre anterior al inicio se rechaza con 400."""
        resp = api_client.post(
            self.URL,
            _payload(start_date="2026-09-01", end_date="2026-08-01"),
        )
        assert resp.status_code == 400
        assert "end_date" in resp.data["errors"]

    def test_list_scoped_to_user(self, api_client) -> None:
        """Cada usuario solo ve sus mensualidades."""
        other = UserFactory()
        Subscription.objects.create(
            user=other, name="Ajeno", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31)
        )
        Subscription.objects.create(
            user=api_client.user, name="Mía", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31)
        )
        resp = api_client.get(self.URL)
        assert resp.status_code == 200
        names = [row["name"] for row in resp.data["results"]]
        assert "Mía" in names
        assert "Ajeno" not in names

    def test_requires_auth(self) -> None:
        """Sin token, 401."""
        resp = APIClient().get(self.URL)
        assert resp.status_code in (401, 403)


@pytest.mark.django_db
class TestSubscriptionProgress:
    """Progreso por tiempo según la fecha de referencia (inyectada)."""

    URL = "/api/subscriptions"

    def test_mid_period(self, api_client, monkeypatch) -> None:
        """A mitad del período devuelve el % transcurrido y estado activa."""
        monkeypatch.setattr("apps.subscriptions.models.timezone.localdate", lambda: date(2026, 8, 1))
        resp = api_client.post(
            self.URL, _payload(start_date="2026-07-01", end_date="2026-09-30")
        )
        # 31 de 91 días transcurridos → 34.1%
        assert resp.data["progress_percent"] == "34.1"
        assert resp.data["status"] == "activa"
        assert resp.data["days_elapsed"] == 31
        assert resp.data["days_total"] == 91

    def test_not_started(self, api_client, monkeypatch) -> None:
        """Antes del inicio: 0% y estado próxima."""
        monkeypatch.setattr("apps.subscriptions.models.timezone.localdate", lambda: date(2026, 6, 1))
        resp = api_client.post(self.URL, _payload())
        assert resp.data["progress_percent"] == "0.0"
        assert resp.data["status"] == "proxima"

    def test_finished(self, api_client, monkeypatch) -> None:
        """Tras el cierre: 100% y estado finalizada."""
        monkeypatch.setattr("apps.subscriptions.models.timezone.localdate", lambda: date(2026, 10, 1))
        resp = api_client.post(self.URL, _payload())
        assert resp.data["progress_percent"] == "100.0"
        assert resp.data["status"] == "finalizada"
