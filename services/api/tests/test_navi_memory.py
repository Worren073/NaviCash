"""Tests de la memoria del asistente Navi (NaviMemory + learn_from_transaction).

Verifica: upsert, refuerzo de usos, extracción de tokens, hook post-registro,
inyección de contexto, comandos explícitos (recuerda/olvida) y endpoints CRUD.
"""

from __future__ import annotations

import pytest

from apps.assistant.memory import (
    extract_main_token,
    forget,
    forget_all,
    handle_forget_command,
    handle_remember_command,
    is_forget_command,
    is_remember_command,
    learn_from_concept,
    learn_from_glossary,
    learn_from_transaction,
    list_memories,
    memory_context,
    normalize_key,
    remember,
)
from apps.assistant.models import NaviMemory
from factories import UserFactory


# ── token extraction ─────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestExtractMainToken:
    def test_extract_simple(self):
        assert extract_main_token("Gasolina del día lunes") == "gasolina"

    def test_extract_stopword_skipped(self):
        # "paga" y "la" son stopwords; "luz" (3 chars) < MIN_TOKEN_LEN=4; "mensual" es válido
        assert extract_main_token("paga la luz mensual") == "mensual"

    def test_extract_short_skipped(self):
        # "el" stopword; "café" (4 chars) alcanza el mínimo → se mantiene
        assert extract_main_token("el café") == "cafe"

    def test_extract_very_short_ignored(self):
        # Tokens menores a 4 chars son ignorados tras stopwords
        assert extract_main_token("el ya un hi") is None

    def test_extract_none_on_empty(self):
        assert extract_main_token("") is None
        assert extract_main_token(None) is None

    def test_extract_accents_stripped(self):
        assert extract_main_token("Comisión bancaria") == "comision"

    def test_extract_all_stopwords_returns_none(self):
        assert extract_main_token("el la de y") is None


# ── normalize ────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestNormalizeKey:
    def test_lower_and_strip(self):
        assert normalize_key("  Wallet_Para : Gasolina  ") == "wallet_para : gasolina"


# ── remember / forget / list ─────────────────────────────────────────────────


@pytest.mark.django_db
class TestRemember:
    def test_creates_new(self):
        user = UserFactory()
        mem = remember(user, "wallet_para:gasolina", "Efectivo")
        assert mem.clave == "wallet_para:gasolina"
        assert mem.valor == "Efectivo"
        assert mem.usos == 1
        assert mem.fuente == NaviMemory.FUENTE_USUARIO

    def test_reinforces_same_value(self):
        user = UserFactory()
        m1 = remember(user, "wallet_para:luz", "Banco de Venezuela")
        m2 = remember(user, "wallet_para:luz", "Banco de Venezuela")
        assert m1.pk == m2.pk
        m2.refresh_from_db()
        assert m2.usos == 2

    def test_replaces_different_value(self):
        user = UserFactory()
        remember(user, "wallet_para:cable", "Efectivo")
        m = remember(user, "wallet_para:cable", "Banco de Venezuela")
        m.refresh_from_db()
        assert m.valor == "Banco de Venezuela"
        assert m.usos == 1


@pytest.mark.django_db
class TestForget:
    def test_forget_existing(self):
        user = UserFactory()
        remember(user, "wallet_para:prueba", "X")
        assert forget(user, "wallet_para:prueba") is True
        assert list_memories(user) == []

    def test_forget_nonexistent(self):
        user = UserFactory()
        assert forget(user, "wallet_para:noexiste") is False


@pytest.mark.django_db
class TestForgetAll:
    def test_forget_all(self):
        user = UserFactory()
        remember(user, "a", "1")
        remember(user, "b", "2")
        assert forget_all(user) == 2
        assert list_memories(user) == []


@pytest.mark.django_db
class TestListMemories:
    def test_order_by_uses(self):
        user = UserFactory()
        remember(user, "raro", "1")
        remember(user, "frecuente", "2")
        remember(user, "frecuente", "2")
        rows = list_memories(user)
        assert rows[0].clave == "frecuente"


# ── learn_from_concept ───────────────────────────────────────────────────────


@pytest.mark.django_db
class TestLearnFromConcept:
    def test_stores_wallet_association(self):
        user = UserFactory()
        learn_from_concept(user, "Gasolina felli", "Efectivo", "pago")
        mems = list_memories(user)
        assert any(m.clave == "wallet_para:gasolina" and m.valor == "Efectivo" for m in mems)

    def test_ignores_no_significant_token(self):
        user = UserFactory()
        # Solo stopwords y tokens muy cortos → nada que almacenar
        learn_from_concept(user, "el ya un", "Efectivo", "pago")
        assert list_memories(user) == []

    def test_ignores_empty_wallet(self):
        user = UserFactory()
        learn_from_concept(user, "Gasolina del lunes", None, "pago")
        assert list_memories(user) == []


# ── learn_from_glossary ─────────────────────────────────────────────────────


@pytest.mark.django_db
class TestLearnFromGlossary:
    def test_lucas_detected(self):
        user = UserFactory()
        learn_from_glossary(user, "Vendí unas lucas", "Efectivo")
        mems = list_memories(user)
        assert any("lucas" in m.clave for m in mems)

    def test_unknown_word_ignored(self):
        user = UserFactory()
        learn_from_glossary(user, "Almuerzo random", "Efectivo")
        assert list_memories(user) == []


# ── learn_from_transaction hook ──────────────────────────────────────────────


@pytest.mark.django_db
class TestLearnFromTransaction:
    def test_hook_stores_association(self):
        user = UserFactory()
        class FakeTx:
            tipo = "pago"
            concepto = "Gasolina del lunes"
            wallet = type("W", (), {"name": "Efectivo"})()
        learn_from_transaction(user, FakeTx())
        mems = list_memories(user)
        assert any(m.clave == "wallet_para:gasolina" for m in mems)

    def test_hook_ignores_transferencia(self):
        user = UserFactory()
        class FakeTx:
            tipo = "transferencia"
            concepto = "Gasolina"
            wallet = None
        learn_from_transaction(user, FakeTx())
        assert list_memories(user) == []

    def test_hook_swallows_exceptions(self):
        user = UserFactory()
        class BrokenTx:
            tipo = "pago"
            concepto = None
            wallet = None
        learn_from_transaction(user, BrokenTx())


# ── memory_context ───────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestMemoryContext:
    def test_returns_associations_and_notes(self):
        user = UserFactory()
        remember(user, "wallet_para:luz", "Banco de Venezuela")
        remember(user, "wallet_para:luz", "Banco de Venezuela")
        remember(user, "personalizado:frase", "Mi frase favorita")
        ctx = memory_context(user)
        assert "luz" in ctx["asociaciones"]
        assert ctx["asociaciones"]["luz"]["wallet"] == "Banco de Venezuela"
        assert "Mi frase favorita" in ctx["notas"]


# ── comandos explícitos ─────────────────────────────────────────────────────


@pytest.mark.django_db
class TestCommandDetection:
    def test_is_remember(self):
        assert is_remember_command("Recuerda que me gusta Efectivo")
        assert is_remember_command("No olvides que el café es en Banesco")

    def test_is_forget(self):
        assert is_forget_command("Olvida que el cable es barato")
        assert is_forget_command("Borra que gasolina es en Efectivo")
        assert is_forget_command("Elimina la asociación de luz")


@pytest.mark.django_db
class TestHandleRemember:
    def test_saves_note(self):
        user = UserFactory()
        resp = handle_remember_command(user, "Recuerda que siempre pago luz el lunes")
        assert "recordaré" in resp.lower()
        mems = list_memories(user)
        assert any(m.fuente == NaviMemory.FUENTE_USUARIO for m in mems)

    def test_rejects_too_short(self):
        user = UserFactory()
        resp = handle_remember_command(user, "Recuerda que sí")
        assert "corta" in resp.lower() or "más" in resp.lower()


@pytest.mark.django_db
class TestHandleForget:
    def test_forgets_note_via_command(self):
        user = UserFactory()
        # Primero crear con el comando real para que la clave coincida
        handle_remember_command(user, "Recuerda que mi billetera es Efectivo")
        resp = handle_forget_command(user, "Olvida mi billetera es efectivo")
        assert "olvidado" in resp.lower() or "olvidé" in resp.lower()

    def test_forgets_wallet_association(self):
        user = UserFactory()
        remember(user, "wallet_para:cable", "Efectivo")
        resp = handle_forget_command(user, "Olvida cable")
        assert "olvidé" in resp.lower() or "olvidado" in resp.lower()

    def test_not_found(self):
        user = UserFactory()
        resp = handle_forget_command(user, "Olvida cosas que no existen")
        assert "no encontré" in resp.lower()


# ── endpoints CRUD ───────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestMemoryAPI:
    def test_list_empty(self, api_client):
        resp = api_client.get("/api/assistant/memory")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_and_list(self, api_client):
        resp = api_client.post(
            "/api/assistant/memory",
            {"texto": "Mi billetera favorita es Efectivo"},
            format="json",
        )
        assert resp.status_code == 201
        assert resp.json()["fuente"] == "usuario"
        resp = api_client.get("/api/assistant/memory")
        assert len(resp.json()) == 1

    def test_delete_all(self, api_client):
        user = api_client.user
        remember(user, "a", "1")
        remember(user, "b", "2")
        resp = api_client.delete("/api/assistant/memory?all=1")
        assert resp.status_code == 200
        assert resp.json()["deleted"] == 2

    def test_delete_by_pk(self, api_client):
        user = api_client.user
        mem = remember(user, "wallet_para:temp", "X")
        resp = api_client.delete(f"/api/assistant/memory/{mem.pk}")
        assert resp.status_code == 204

    def test_delete_nonexistent(self, api_client):
        import uuid
        resp = api_client.delete(f"/api/assistant/memory/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_delete_no_param_returns_400(self, api_client):
        resp = api_client.delete("/api/assistant/memory")
        assert resp.status_code == 400
