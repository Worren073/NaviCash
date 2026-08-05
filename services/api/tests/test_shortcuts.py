"""tests — Atajos del home (CRUD owner-scoped)."""

from __future__ import annotations

import pytest

from factories import UserFactory


@pytest.mark.django_db
class TestShortcuts:
    """CRUD de atajos en /api/shortcuts."""

    URL = "/api/shortcuts"

    def test_create_shortcut(self, api_client) -> None:
        """Crear un atajo de tipo transaction."""
        resp = api_client.post(
            self.URL,
            {
                "label": "Cobrar a María",
                "kind": "transaction",
                "config": {"tipo": "cobro", "monto": "20.00", "moneda": "USD"},
                "order": 1,
            },
            format="json",
        )
        assert resp.status_code == 201
        assert resp.data["label"] == "Cobrar a María"

    def test_shortcuts_owned_by_user(self, api_client) -> None:
        """El atajo queda ligado al usuario autenticado."""
        resp = api_client.post(self.URL, {"label": "Aporte", "kind": "goal_contribution"})
        assert resp.status_code == 201
        from apps.shortcuts.models import Shortcut

        assert Shortcut.objects.get(pk=resp.data["id"]).user == api_client.user

    def test_list_only_own(self, auth_client_factory) -> None:
        """El listado solo muestra los atajos propios."""
        other = UserFactory()
        from apps.shortcuts.models import Shortcut

        Shortcut.objects.create(user=other, label="Ajeno", kind="transaction")
        client = auth_client_factory()
        resp = client.get(self.URL)
        assert resp.status_code == 200
        assert resp.data["count"] == 0

    def test_cannot_delete_other_shortcut(self, auth_client_factory) -> None:
        """Borrar un atajo ajeno falla."""
        other = UserFactory()
        from apps.shortcuts.models import Shortcut

        shortcut = Shortcut.objects.create(user=other, label="Ajeno", kind="transaction")
        client = auth_client_factory()
        resp = client.delete(f"/api/shortcuts/{shortcut.id}")
        assert resp.status_code in (403, 404)