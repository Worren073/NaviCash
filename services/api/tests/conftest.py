"""Fixtures compartidos por todos los tests de NaviCash.

- ``api_client``: cliente APIClient autenticado como un usuario activo.
- ``auth_client``: fábrica de clientes autenticados (crea usuario nuevo por
  cliente) para tests que necesitan AISLAMIENTO entre usuarios.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from factories import UserFactory


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    """Vacía la cache entre tests.

    El rate limit del asistente guarda contadores con TTL largo en Redis
    (persiste entre corridas): como los PK de usuario se reutilizan entre
    corridas, un contador viejo (ej. 30/h agotado) le caería a otro usuario
    en la siguiente ejecución. Limpiar por test mantiene el aislamiento.
    """
    from django.core.cache import cache

    cache.clear()
    yield


@pytest.fixture
def api_client() -> APIClient:
    """Cliente APIClient autenticado con un usuario activo (Bearer token).

    El usuario autenticado queda disponible en ``client.user``.

    Credenciales por defecto:
        email: user0@example.com (secuencial de la factory).
        password: "test-password-123".
    """
    user = UserFactory()
    token = _access_token(user)
    client = APIClient()
    client.user = user
    client.user_password = "test-password-123"
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


@pytest.fixture
def auth_client_factory():
    """Fábrica que devuelve un APIClient autenticado por usuario distinto.

    Uso: ``client = auth_client_factory(user)`` o ``client = auth_client_factory()``
    para crear un usuario nuevo. El usuario queda en ``client.user``.
    """
    def _build(user=None) -> APIClient:
        user = user or UserFactory()
        client = APIClient()
        token = _access_token(user)
        client.user = user
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        return client

    return _build


def _access_token(user) -> str:
    """Emite un JWT access para el usuario de prueba."""
    from rest_framework_simplejwt.tokens import RefreshToken

    return str(RefreshToken.for_user(user).access_token)