"""tests — Conversión de moneda cross-currency en el asistente Navi.

Verifica que la conversión USD↔VES funcione correctamente en:
- tools.py: _exec_register_preview, _monto_converted_preview
- services.py: _execute_ledger con proposal.tasa
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import pytest

from apps.assistant.actions import ActionProposal
from apps.assistant.tools import _exec_register_preview, _monto_converted_preview


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ctx(
    wallets: list[dict] | None = None,
    rate: str | None = "36.50",
) -> dict:
    if wallets is None:
        wallets = [
            {"name": "Banesco", "currency": "VES", "saldo": "50000", "tipo": "bank"},
        ]
    return {"wallets": wallets, "base_currency": "USD", "rate": rate}


# ---------------------------------------------------------------------------
# _monto_converted_preview: cálculos de conversión
# ---------------------------------------------------------------------------


class TestMontoConvertedMath:
    """Verifica las matemáticas de conversión en el helper."""

    def test_usd_to_ves_bcv(self) -> None:
        """2.5 USD * 36.50 = 91.25 VES (BCV)."""
        wallet = {"name": "Banesco", "currency": "VES"}
        result = _monto_converted_preview("pago", 2.5, "USD", wallet, "Test", Decimal("36.50"), "bcv")
        assert Decimal(result["monto_convertido"]) == Decimal("91.25")

    def test_usd_to_ves_custom(self) -> None:
        """2.5 USD * 880 = 2200.00 VES (personalizada)."""
        wallet = {"name": "Banesco", "currency": "VES"}
        result = _monto_converted_preview("pago", 2.5, "USD", wallet, "Test", Decimal("880"), "personalizada")
        assert Decimal(result["monto_convertido"]) == Decimal("2200.00")

    def test_ves_to_usd_bcv(self) -> None:
        """1000 VES / 36.50 = 27.40 USD (BCV)."""
        wallet = {"name": "Efectivo", "currency": "USD"}
        result = _monto_converted_preview("pago", 1000, "VES", wallet, "Test", Decimal("36.50"), "bcv")
        assert Decimal(result["monto_convertido"]) == Decimal("27.40")

    def test_ves_to_usd_custom(self) -> None:
        """1000 VES / 40 = 25.00 USD (personalizada)."""
        wallet = {"name": "Efectivo", "currency": "USD"}
        result = _monto_converted_preview("pago", 1000, "VES", wallet, "Test", Decimal("40"), "personalizada")
        assert Decimal(result["monto_convertido"]) == Decimal("25.00")

    def test_large_amount(self) -> None:
        """100000 USD * 880 = 88,000,000 VES."""
        wallet = {"name": "Banesco", "currency": "VES"}
        result = _monto_converted_preview("cobro", 100000, "USD", wallet, "Salario", Decimal("880"), "personalizada")
        assert Decimal(result["monto_convertido"]) == Decimal("88000000.00")

    def test_small_amount(self) -> None:
        """0.50 USD * 36.50 = 18.25 VES."""
        wallet = {"name": "Banesco", "currency": "VES"}
        result = _monto_converted_preview("pago", 0.5, "USD", wallet, "Café", Decimal("36.50"), "bcv")
        assert Decimal(result["monto_convertido"]) == Decimal("18.25")


# ---------------------------------------------------------------------------
# _exec_register_preview: detección de mismatch y rate handling
# ---------------------------------------------------------------------------


class TestCurrencyMismatchDetection:
    """Detección de mismatch moneda vs wallet."""

    def test_mismatch_no_rate_returns_currency_mismatch(self) -> None:
        """USD en VES sin tasa → currency_mismatch."""
        ctx = _ctx(rate=None)
        result = _exec_register_preview(
            {"tipo": "pago", "monto": 10, "moneda": "USD", "wallet": "Banesco"},
            ctx,
        )
        assert result["status"] == "currency_mismatch"
        assert result["moneda_solicitada"] == "USD"
        assert result["moneda_cuenta"] == "VES"

    def test_bcv_rate_from_context(self) -> None:
        """Rate del contexto se usa con tipo_tasa='bcv'."""
        ctx = _ctx(rate="36.50")
        result = _exec_register_preview(
            {"tipo": "pago", "monto": 10, "moneda": "USD", "wallet": "Banesco", "tipo_tasa": "bcv"},
            ctx,
        )
        assert result["status"] == "pending_confirmation"
        assert result["convertir"] is True
        assert result["tasa"] == "36.50"
        assert result["tipo_tasa"] == "bcv"

    def test_custom_rate_overrides_bcv(self) -> None:
        """Tasa personalizada reemplaza la del contexto."""
        ctx = _ctx(rate="36.50")
        result = _exec_register_preview(
            {"tipo": "pago", "monto": 10, "moneda": "USD", "wallet": "Banesco", "tasa": 880},
            ctx,
        )
        assert result["status"] == "pending_confirmation"
        assert result["tasa"] == "880"
        assert result["tipo_tasa"] == "personalizada"
        # 10 * 880 = 8800, no 10 * 36.50
        assert Decimal(result["monto_convertido"]) == Decimal("8800.00")

    def test_rate_zero_returns_error(self) -> None:
        """Tasa=0 → error."""
        ctx = _ctx()
        result = _exec_register_preview(
            {"tipo": "pago", "monto": 10, "moneda": "USD", "wallet": "Banesco", "tasa": 0},
            ctx,
        )
        assert result["status"] == "error"
        assert "tasa" in result["message"].lower()

    def test_rate_negative_returns_error(self) -> None:
        """Tasa negativa → error."""
        ctx = _ctx()
        result = _exec_register_preview(
            {"tipo": "pago", "monto": 10, "moneda": "USD", "wallet": "Banesco", "tasa": -5},
            ctx,
        )
        assert result["status"] == "error"

    def test_bcv_rate_unavailable_returns_error(self) -> None:
        """tipo_tasa='bcv' pero rate=None → error."""
        ctx = _ctx(rate=None)
        result = _exec_register_preview(
            {"tipo": "pago", "monto": 10, "moneda": "USD", "wallet": "Banesco", "tipo_tasa": "bcv"},
            ctx,
        )
        assert result["status"] == "error"
        assert "tasa" in result["message"].lower()


# ---------------------------------------------------------------------------
# _execute_ledger: usa proposal.tasa
# ---------------------------------------------------------------------------


class TestExecuteLedgerConversion:
    """_execute_ledger usa proposal.tasa cuando existe."""

    @pytest.fixture
    def _seed_rate(self):
        """Siembra tasa oficial para conversiones."""
        from apps.rates.models import ExchangeRate
        from django.utils import timezone

        if not ExchangeRate.objects.filter(source="oficial").exists():
            ExchangeRate.objects.create(
                source="oficial",
                currency="VES",
                promedio=Decimal("61.94"),
                rate_date=timezone.now(),
            )

    @pytest.mark.django_db
    def test_execute_ledger_uses_proposal_tasa(self, api_client, _seed_rate) -> None:
        """_execute_ledger usa proposal.tasa en vez de la tasa oficial."""
        from apps.assistant.services import _execute_ledger
        from apps.wallets.models import Wallet

        wallet = Wallet.objects.create(
            user=api_client.user, name="Banesco", currency="VES", saldo=Decimal("50000"),
        )
        proposal = ActionProposal(
            tipo="pago",
            monto=Decimal("2.5"),
            moneda="VES",
            moneda_original="USD",
            convertir=True,
            tasa=Decimal("880"),
            tipo_tasa="personalizada",
            concepto="Test",
            wallet_name="Banesco",
        )
        result = _execute_ledger(api_client.user, proposal)
        # 2.5 * 880 = 2200.00
        assert "2,200.00" in result
        wallet.refresh_from_db()
        assert wallet.saldo == Decimal("47800.00")

    @pytest.mark.django_db
    def test_execute_ledger_falls_back_to_official(self, api_client, _seed_rate) -> None:
        """Sin proposal.tasa → usa get_usd_rate_for_conversion()."""
        from apps.assistant.services import _execute_ledger
        from apps.wallets.models import Wallet

        wallet = Wallet.objects.create(
            user=api_client.user, name="Banesco", currency="VES", saldo=Decimal("50000"),
        )
        proposal = ActionProposal(
            tipo="cobro",
            monto=Decimal("100"),
            moneda="VES",
            moneda_original="USD",
            convertir=True,
            concepto="Salario",
            wallet_name="Banesco",
        )
        result = _execute_ledger(api_client.user, proposal)
        # 100 * 61.94 = 6194.00
        assert "6,194.00" in result
        wallet.refresh_from_db()
        assert wallet.saldo == Decimal("56194.00")

    @pytest.mark.django_db
    def test_execute_ledger_no_conversion_same_currency(self, api_client) -> None:
        """Sin convertir → monto se registra directo."""
        from apps.assistant.services import _execute_ledger
        from apps.wallets.models import Wallet

        wallet = Wallet.objects.create(
            user=api_client.user, name="Efectivo", currency="USD", saldo=Decimal("500"),
        )
        proposal = ActionProposal(
            tipo="pago",
            monto=Decimal("50"),
            moneda="USD",
            concepto="Test",
            wallet_name="Efectivo",
        )
        result = _execute_ledger(api_client.user, proposal)
        assert "50.00" in result
        wallet.refresh_from_db()
        assert wallet.saldo == Decimal("450.00")

    @pytest.mark.django_db
    def test_execute_ledger_rate_one_returns_error(self, api_client) -> None:
        """tasa=1 → 'No tengo disponible la tasa' (rate <= 1)."""
        from apps.assistant.services import _execute_ledger
        from apps.wallets.models import Wallet

        Wallet.objects.create(
            user=api_client.user, name="Banesco", currency="VES", saldo=Decimal("50000"),
        )
        proposal = ActionProposal(
            tipo="pago",
            monto=Decimal("100"),
            moneda="VES",
            moneda_original="USD",
            convertir=True,
            tasa=Decimal("1"),
            tipo_tasa="personalizada",
            concepto="Test",
            wallet_name="Banesco",
        )
        result = _execute_ledger(api_client.user, proposal)
        assert "No tengo disponible" in result
