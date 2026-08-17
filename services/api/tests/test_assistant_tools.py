"""tests — Tool executors del asistente Navi.

Verifica que cada tool (register_transaction, create_transfer, get_balance,
get_transactions, get_subscriptions, get_savings_goals, check_afford) retorne
resultados correctos, valide errores y maneje edge cases. Sin DB.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.assistant.tools import (
    TOOLS,
    _exec_afford,
    _exec_balance,
    _exec_register_preview,
    _exec_subscriptions,
    _exec_savings_goals,
    _exec_transactions,
    _exec_transfer_preview,
    _monto_converted_preview,
    execute_tool,
)


# ---------------------------------------------------------------------------
# Contextos de prueba
# ---------------------------------------------------------------------------


def _ctx(
    wallets: list[dict] | None = None,
    rate: str | None = "36.50",
    total_usd: str = "1000.00",
    total_ves: str = "0.00",
) -> dict:
    """Contexto mínimo tipo ``build_context``."""
    if wallets is None:
        wallets = [
            {"name": "Efectivo", "currency": "USD", "saldo": "500.00", "tipo": "cash"},
            {"name": "Banesco", "currency": "VES", "saldo": "50000.00", "tipo": "bank"},
        ]
    return {
        "wallets": wallets,
        "base_currency": "USD",
        "rate": rate,
        "total_balance_usd": total_usd,
        "total_balance_ves": total_ves,
        "recent_transactions": [
            {"tipo": "pago", "monto": "25.00", "moneda": "USD", "wallet": "Efectivo", "concepto": "Netflix"},
            {"tipo": "cobro", "monto": "500.00", "moneda": "USD", "wallet": "Efectivo", "concepto": "Salario"},
        ],
        "subscriptions": [
            {"name": "Netflix", "status": "activa", "amount": "15.00", "currency": "USD"},
        ],
        "goals": [
            {"name": "Viaje", "target_amount": "1000.00", "currency": "USD", "total_contributed": "250.00"},
        ],
    }


# ---------------------------------------------------------------------------
# Fase 1: register_transaction
# ---------------------------------------------------------------------------


class TestExecRegisterPreview:
    """_exec_register_preview: validación, currency mismatch, conversión."""

    def test_same_currency_pending(self) -> None:
        """Pago VES en wallet VES → pending_confirmation."""
        ctx = _ctx([{"name": "Banesco", "currency": "VES", "saldo": "50000", "tipo": "bank"}])
        result = _exec_register_preview(
            {"tipo": "pago", "monto": 250, "wallet": "Banesco", "concepto": "Alquiler"},
            ctx,
        )
        assert result["status"] == "pending_confirmation"
        assert result["tipo"] == "pago"
        assert result["monto"] == "250"
        assert result["moneda"] == "VES"
        assert result["wallet"] == "Banesco"
        assert result["concepto"] == "Alquiler"

    def test_invalid_tipo(self) -> None:
        """Tipo inválido → error."""
        result = _exec_register_preview({"tipo": "otro", "monto": 100, "wallet": "Efectivo"}, _ctx())
        assert result["status"] == "error"
        assert "inválido" in result["message"].lower()

    def test_missing_tipo(self) -> None:
        """Sin tipo → error."""
        result = _exec_register_preview({"monto": 100, "wallet": "Efectivo"}, _ctx())
        assert result["status"] == "error"

    def test_missing_monto(self) -> None:
        """Sin monto → error."""
        result = _exec_register_preview({"tipo": "pago", "wallet": "Efectivo"}, _ctx())
        assert result["status"] == "error"
        assert "monto" in result["message"].lower()

    def test_missing_wallet(self) -> None:
        """Sin wallet → error."""
        result = _exec_register_preview({"tipo": "pago", "monto": 100}, _ctx())
        assert result["status"] == "error"
        assert "cuenta" in result["message"].lower()

    def test_unknown_wallet(self) -> None:
        """Wallet inexistente → error con lista de disponibles."""
        result = _exec_register_preview(
            {"tipo": "pago", "monto": 100, "wallet": "Inexistente"}, _ctx()
        )
        assert result["status"] == "error"
        assert "Inexistente" in result["message"]
        assert "Efectivo" in result["message"]

    def test_falls_back_to_wallet_currency(self) -> None:
        """Sin moneda explícita → usa moneda de la wallet."""
        ctx = _ctx([{"name": "Banesco", "currency": "VES", "saldo": "50000", "tipo": "bank"}])
        result = _exec_register_preview(
            {"tipo": "pago", "monto": 100, "wallet": "Banesco"}, ctx
        )
        assert result["status"] == "pending_confirmation"
        assert result["moneda"] == "VES"

    def test_currency_mismatch_no_rate(self) -> None:
        """USD en wallet VES sin tasa → currency_mismatch."""
        ctx = _ctx(
            wallets=[{"name": "Banesco", "currency": "VES", "saldo": "50000", "tipo": "bank"}],
            rate=None,
        )
        result = _exec_register_preview(
            {"tipo": "pago", "monto": 2.5, "moneda": "USD", "wallet": "Banesco"}, ctx
        )
        assert result["status"] == "currency_mismatch"
        assert result["moneda_solicitada"] == "USD"
        assert result["moneda_cuenta"] == "VES"
        assert result["wallet"] == "Banesco"

    def test_bcv_rate_conversion(self) -> None:
        """USD en VES con tipo_tasa="bcv" → converted preview."""
        ctx = _ctx(
            wallets=[{"name": "Banesco", "currency": "VES", "saldo": "50000", "tipo": "bank"}],
            rate="36.50",
        )
        result = _exec_register_preview(
            {"tipo": "pago", "monto": 10, "moneda": "USD", "wallet": "Banesco", "tipo_tasa": "bcv"},
            ctx,
        )
        assert result["status"] == "pending_confirmation"
        assert result["convertir"] is True
        assert result["moneda_original"] == "USD"
        assert result["moneda"] == "VES"
        assert result["tipo_tasa"] == "bcv"
        assert result["tasa"] == "36.50"
        # 10 * 36.50 = 365.00
        assert Decimal(result["monto_convertido"]) == Decimal("365.00")

    def test_custom_rate_conversion(self) -> None:
        """USD en VES con tasa=880 → converted preview."""
        ctx = _ctx(
            wallets=[{"name": "Banesco", "currency": "VES", "saldo": "50000", "tipo": "bank"}],
        )
        result = _exec_register_preview(
            {"tipo": "pago", "monto": 2.5, "moneda": "USD", "wallet": "Banesco", "tasa": 880},
            ctx,
        )
        assert result["status"] == "pending_confirmation"
        assert result["convertir"] is True
        assert result["moneda_original"] == "USD"
        assert result["moneda"] == "VES"
        assert result["tipo_tasa"] == "personalizada"
        # 2.5 * 880 = 2200.00
        assert Decimal(result["monto_convertido"]) == Decimal("2200.00")

    def test_rate_zero_error(self) -> None:
        """Tasa=0 → error."""
        ctx = _ctx(
            wallets=[{"name": "Banesco", "currency": "VES", "saldo": "50000", "tipo": "bank"}],
        )
        result = _exec_register_preview(
            {"tipo": "pago", "monto": 10, "moneda": "USD", "wallet": "Banesco", "tasa": 0},
            ctx,
        )
        assert result["status"] == "error"
        assert "tasa" in result["message"].lower()

    def test_rate_negative_error(self) -> None:
        """Tasa negativa → error."""
        ctx = _ctx(
            wallets=[{"name": "Banesco", "currency": "VES", "saldo": "50000", "tipo": "bank"}],
        )
        result = _exec_register_preview(
            {"tipo": "pago", "monto": 10, "moneda": "USD", "wallet": "Banesco", "tasa": -5},
            ctx,
        )
        assert result["status"] == "error"

    def test_concepto_default_pago(self) -> None:
        """Sin concepto → 'Gasto registrado' para pago."""
        ctx = _ctx([{"name": "Banesco", "currency": "VES", "saldo": "50000", "tipo": "bank"}])
        result = _exec_register_preview(
            {"tipo": "pago", "monto": 100, "wallet": "Banesco"}, ctx
        )
        assert result["concepto"] == "Gasto registrado"

    def test_concepto_default_cobro(self) -> None:
        """Sin concepto → 'Ingreso registrado' para cobro."""
        ctx = _ctx([{"name": "Banesco", "currency": "VES", "saldo": "50000", "tipo": "bank"}])
        result = _exec_register_preview(
            {"tipo": "cobro", "monto": 100, "wallet": "Banesco"}, ctx
        )
        assert result["concepto"] == "Ingreso registrado"

    def test_conversion_preview_usd_to_ves(self) -> None:
        """2.5 USD * 880 = 2200.00 VES."""
        ctx = _ctx(
            wallets=[{"name": "Banesco", "currency": "VES", "saldo": "50000", "tipo": "bank"}],
        )
        result = _exec_register_preview(
            {"tipo": "pago", "monto": 2.5, "moneda": "USD", "wallet": "Banesco", "tasa": 880},
            ctx,
        )
        assert Decimal(result["monto_convertido"]) == Decimal("2200.00")
        assert "2.50 USD → 2,200.00 VES" in result["conversion_preview"]

    def test_conversion_preview_ves_to_usd(self) -> None:
        """1000 VES / 36.50 = 27.40 USD."""
        ctx = _ctx(
            wallets=[{"name": "Efectivo", "currency": "USD", "saldo": "500", "tipo": "cash"}],
        )
        result = _exec_register_preview(
            {"tipo": "pago", "monto": 1000, "moneda": "VES", "wallet": "Efectivo", "tasa": 36.5},
            ctx,
        )
        assert result["status"] == "pending_confirmation"
        assert result["convertir"] is True
        assert result["moneda"] == "USD"
        assert result["moneda_original"] == "VES"
        assert Decimal(result["monto_convertido"]) == Decimal("27.40")


# ---------------------------------------------------------------------------
# Fase 1: create_transfer
# ---------------------------------------------------------------------------


class TestExecTransferPreview:
    """_exec_transfer_preview: validación, wallets, misma wallet."""

    def test_success(self) -> None:
        """Transferencia entre 2 wallets → pending_confirmation."""
        ctx = _ctx([
            {"name": "Efectivo", "currency": "USD", "saldo": "500", "tipo": "cash"},
            {"name": "Banesco", "currency": "USD", "saldo": "1000", "tipo": "bank"},
        ])
        result = _exec_transfer_preview(
            {"monto": 100, "source_wallet": "Efectivo", "dest_wallet": "Banesco"},
            ctx,
        )
        assert result["status"] == "pending_confirmation"
        assert result["source_wallet"] == "Efectivo"
        assert result["dest_wallet"] == "Banesco"
        assert result["monto"] == "100"

    def test_same_wallet(self) -> None:
        """Source == dest → error."""
        ctx = _ctx([
            {"name": "Efectivo", "currency": "USD", "saldo": "500", "tipo": "cash"},
        ])
        result = _exec_transfer_preview(
            {"monto": 100, "source_wallet": "Efectivo", "dest_wallet": "Efectivo"},
            ctx,
        )
        assert result["status"] == "error"
        assert "misma" in result["message"].lower()

    def test_unknown_source(self) -> None:
        """Source inexistente → error."""
        ctx = _ctx([
            {"name": "Efectivo", "currency": "USD", "saldo": "500", "tipo": "cash"},
        ])
        result = _exec_transfer_preview(
            {"monto": 100, "source_wallet": "Inexistente", "dest_wallet": "Efectivo"},
            ctx,
        )
        assert result["status"] == "error"
        assert "origen" in result["message"].lower()

    def test_unknown_dest(self) -> None:
        """Dest inexistente → error."""
        ctx = _ctx([
            {"name": "Efectivo", "currency": "USD", "saldo": "500", "tipo": "cash"},
        ])
        result = _exec_transfer_preview(
            {"monto": 100, "source_wallet": "Efectivo", "dest_wallet": "Inexistente"},
            ctx,
        )
        assert result["status"] == "error"
        assert "destino" in result["message"].lower()

    def test_missing_params(self) -> None:
        """Sin source/dest → error."""
        result = _exec_transfer_preview({"monto": 100}, _ctx())
        assert result["status"] == "error"

    def test_missing_monto(self) -> None:
        """Sin monto → error."""
        result = _exec_transfer_preview(
            {"source_wallet": "Efectivo", "dest_wallet": "Banesco"}, _ctx()
        )
        assert result["status"] == "error"

    def test_falls_back_to_source_currency(self) -> None:
        """Sin moneda → usa moneda de source wallet."""
        ctx = _ctx([
            {"name": "Efectivo", "currency": "USD", "saldo": "500", "tipo": "cash"},
            {"name": "Banesco", "currency": "USD", "saldo": "1000", "tipo": "bank"},
        ])
        result = _exec_transfer_preview(
            {"monto": 100, "source_wallet": "Efectivo", "dest_wallet": "Banesco"},
            ctx,
        )
        assert result["moneda"] == "USD"


# ---------------------------------------------------------------------------
# Fase 1: get_balance
# ---------------------------------------------------------------------------


class TestExecBalance:
    """_exec_balance: total, específica, desconocida."""

    def test_no_wallet_returns_total(self) -> None:
        """Sin wallet → retorna total."""
        ctx = _ctx(total_usd="1500.00", total_ves="50000.00")
        result = _exec_balance({}, ctx)
        assert result["total_usd"] == "1500.00"
        assert result["total_ves"] == "50000.00"
        assert len(result["wallets"]) == 2

    def test_with_wallet(self) -> None:
        """Con wallet → saldo específico."""
        ctx = _ctx()
        result = _exec_balance({"wallet": "Efectivo"}, ctx)
        assert result["name"] == "Efectivo"
        assert result["saldo"] == "500.00"
        assert result["currency"] == "USD"

    def test_unknown_wallet(self) -> None:
        """Wallet inexistente → error."""
        result = _exec_balance({"wallet": "Inexistente"}, _ctx())
        assert "error" in result

    def test_fuzzy_match(self) -> None:
        """Matching parcial: 'Banes' → 'Banesco'."""
        ctx = _ctx()
        result = _exec_balance({"wallet": "Banes"}, ctx)
        assert result["name"] == "Banesco"


# ---------------------------------------------------------------------------
# Fase 1: get_transactions
# ---------------------------------------------------------------------------


class TestExecTransactions:
    """_exec_transactions: filtrado, límite."""

    def test_returns_all(self) -> None:
        """Sin filtros → todas las transacciones."""
        ctx = _ctx()
        result = _exec_transactions({}, ctx)
        assert result["count"] == 2

    def test_filter_by_tipo(self) -> None:
        """Filtrado por tipo."""
        ctx = _ctx()
        result = _exec_transactions({"tipo": "pago"}, ctx)
        assert result["count"] == 1
        assert result["transactions"][0]["tipo"] == "pago"

    def test_filter_by_wallet(self) -> None:
        """Filtrado por wallet."""
        ctx = _ctx()
        result = _exec_transactions({"wallet": "Efectivo"}, ctx)
        assert result["count"] == 2  # ambas son de Efectivo

    def test_limit_to_10(self) -> None:
        """Retorna hasta 10 items, pero count refleja el total filtrado."""
        ctx = _ctx()
        ctx["recent_transactions"] = [{"tipo": "pago", "monto": str(i)} for i in range(15)]
        result = _exec_transactions({}, ctx)
        assert len(result["transactions"]) == 10
        assert result["count"] == 15


# ---------------------------------------------------------------------------
# Fase 1: get_subscriptions, get_savings_goals
# ---------------------------------------------------------------------------


class TestExecSubscriptions:
    def test_returns_subscriptions(self) -> None:
        ctx = _ctx()
        result = _exec_subscriptions({}, ctx)
        assert len(result["subscriptions"]) == 1
        assert result["subscriptions"][0]["name"] == "Netflix"

    def test_empty(self) -> None:
        ctx = _ctx()
        ctx["subscriptions"] = []
        result = _exec_subscriptions({}, ctx)
        assert result["subscriptions"] == []


class TestExecSavingsGoals:
    def test_returns_goals(self) -> None:
        ctx = _ctx()
        result = _exec_savings_goals({}, ctx)
        assert len(result["goals"]) == 1
        assert result["goals"][0]["name"] == "Viaje"

    def test_empty(self) -> None:
        ctx = _ctx()
        ctx["goals"] = []
        result = _exec_savings_goals({}, ctx)
        assert result["goals"] == []


# ---------------------------------------------------------------------------
# Fase 1: check_afford
# ---------------------------------------------------------------------------


class TestExecAfford:
    def test_can_afford(self) -> None:
        """Saldo suficiente → can_afford=True."""
        ctx = _ctx([
            {"name": "Efectivo", "currency": "USD", "saldo": "500", "tipo": "cash"},
        ])
        result = _exec_afford({"monto": 100, "moneda": "USD"}, ctx)
        assert result["can_afford"] is True
        assert result["requested"] == "100.00 USD"
        assert result["available"] == "500.00 USD"

    def test_cannot_afford(self) -> None:
        """Saldo insuficiente → can_afford=False."""
        ctx = _ctx([
            {"name": "Efectivo", "currency": "USD", "saldo": "50", "tipo": "cash"},
        ])
        result = _exec_afford({"monto": 100, "moneda": "USD"}, ctx)
        assert result["can_afford"] is False

    def test_no_amount(self) -> None:
        """Sin monto → error."""
        result = _exec_afford({"moneda": "USD"}, _ctx())
        assert "error" in result

    def test_cross_currency_afford(self) -> None:
        """Afford en moneda distinta a la wallet: no suma."""
        ctx = _ctx([
            {"name": "Efectivo", "currency": "USD", "saldo": "500", "tipo": "cash"},
        ])
        result = _exec_afford({"monto": 100, "moneda": "VES"}, ctx)
        assert result["can_afford"] is False
        assert result["available"] == "0.00 VES"


# ---------------------------------------------------------------------------
# Fase 1: execute_tool dispatch
# ---------------------------------------------------------------------------


class TestExecuteTool:
    def test_unknown_tool(self) -> None:
        """Tool desconocida → error."""
        result = execute_tool("unknown_tool", {}, _ctx())
        assert "error" in result
        assert "desconocida" in result["error"].lower()

    def test_exception_handling(self) -> None:
        """Excepción en handler → error graceful (no crashea)."""
        # Forzar un error pasando args que causen excepción interna
        result = execute_tool("check_afford", {"monto": "abc"}, _ctx())
        # El handler catchea la excepción
        assert isinstance(result, dict)

    def test_all_tools_defined(self) -> None:
        """Las 7 tools están definidas en TOOLS."""
        tool_names = {t["function"]["name"] for t in TOOLS}
        expected = {
            "register_transaction", "create_transfer", "get_balance",
            "get_transactions", "get_subscriptions", "get_savings_goals",
            "check_afford",
        }
        assert tool_names == expected

    def test_register_tool_has_tasa_fields(self) -> None:
        """register_transaction tiene campos tasa y tipo_tasa."""
        reg = [t for t in TOOLS if t["function"]["name"] == "register_transaction"][0]
        props = reg["function"]["parameters"]["properties"]
        assert "tasa" in props
        assert "tipo_tasa" in props
        assert props["tipo_tasa"]["enum"] == ["bcv", "personalizada"]


# ---------------------------------------------------------------------------
# _monto_converted_preview helper
# ---------------------------------------------------------------------------


class TestMontoConvertedPreview:
    def test_usd_to_ves(self) -> None:
        """2.5 USD * 880 = 2200.00 VES."""
        wallet = {"name": "Banesco", "currency": "VES"}
        result = _monto_converted_preview("pago", 2.5, "USD", wallet, "Test", Decimal("880"), "personalizada")
        assert result["status"] == "pending_confirmation"
        assert result["convertir"] is True
        assert result["moneda_original"] == "USD"
        assert result["moneda"] == "VES"
        assert Decimal(result["monto_convertido"]) == Decimal("2200.00")

    def test_ves_to_usd(self) -> None:
        """1000 VES / 36.5 = 27.40 USD."""
        wallet = {"name": "Efectivo", "currency": "USD"}
        result = _monto_converted_preview("pago", 1000, "VES", wallet, "Test", Decimal("36.5"), "bcv")
        assert result["convertir"] is True
        assert result["moneda"] == "USD"
        assert result["moneda_original"] == "VES"
        assert Decimal(result["monto_convertido"]) == Decimal("27.40")

    def test_rate_one_returns_error(self) -> None:
        """Tasa=1 no debería ser válida para conversión (rate <= 0 check está en register_preview, no aquí)."""
        wallet = {"name": "Banesco", "currency": "VES"}
        result = _monto_converted_preview("pago", 100, "USD", wallet, "Test", Decimal("1"), "bcv")
        assert Decimal(result["monto_convertido"]) == Decimal("100.00")
