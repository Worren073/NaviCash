"""tests — endpoint de salud ``/api/health`` (keep-alive de Render)."""

from __future__ import annotations


def test_health_sin_auth_responde_ok(client) -> None:
    """GET /api/health responde 200 sin credenciales."""
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_health_no_esta_throttled(client) -> None:
    """No consume el presupuesto anon (60/min): 70 llamadas seguidas → 200."""
    for _ in range(70):
        assert client.get("/api/health").status_code == 200
