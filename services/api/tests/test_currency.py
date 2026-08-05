"""tests — Reglas de oro del manejo de dinero (core.currency)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.core.currency import (
    REFERENCE_CURRENCY,
    amount_to_minor,
    convert_to_usd,
    is_valid_amount,
    round_money,
    to_decimal,
    usd_to_currency,
)


class TestRoundMoney:
    """Redondeo a 2 decimales con política mitad-hacia-arriba."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("12.345", "12.35"),
            ("12.344", "12.34"),
            ("10.009", "10.01"),
            ("0.005", "0.01"),
            ("-1.295", "-1.30"),
        ],
    )
    def test_round_half_up(self, raw: str, expected: str) -> None:
        """Redondea correcto hacia arriba/abajo según la política elegida."""
        assert str(round_money(Decimal(raw))) == expected


class TestValidAmount:
    """Validación de montos (positivos y >= 0.01)."""

    def test_accepts_positive(self) -> None:
        """Acepta montos positivos con céntimos."""
        assert is_valid_amount(Decimal("12.00")) is True

    def test_rejects_zero(self) -> None:
        """Rechaza 0."""
        assert is_valid_amount(Decimal("0")) is False

    def test_rejects_negative(self) -> None:
        """Rechaza negativos."""
        assert is_valid_amount(Decimal("-5")) is False

    def test_rejects_non_decimal(self) -> None:
        """Rechaza tipos no Decimal (seguridad anti-float)."""
        assert is_valid_amount(12.0) is False  # noqa: E721


class TestConversion:
    """Conversiones USD <-> moneda local con tasa oficial."""

    def test_usd_is_identity(self) -> None:
        """Convertir USD a USD no debe cambiar el monto."""
        assert convert_to_usd(Decimal("50.00"), "USD", Decimal("100")) == Decimal("50.00")

    def test_ves_to_usd(self) -> None:
        """50 VES a 100 VES/USD => 0.50 USD."""
        assert convert_to_usd(Decimal("50.00"), "VES", Decimal("100")) == Decimal("0.50")

    def test_usd_to_ves(self) -> None:
        """0.50 USD a 100 VES/USD => 50.00 VES."""
        assert usd_to_currency(Decimal("0.50"), "VES", Decimal("100")) == Decimal("50.00")

    def test_inverse_direction(self) -> None:
        """Comprobación de ida y vuelta: USD -> VES -> USD."""
        raw = Decimal("123.45")
        ves = usd_to_currency(raw, "VES", Decimal("100"))
        back = convert_to_usd(ves, "VES", Decimal("100"))
        assert back == raw

    def test_rejects_non_positive_rate(self) -> None:
        """Tasa <= 0 debe lanzar ValueError."""
        with pytest.raises(ValueError):
            convert_to_usd(Decimal("10"), "VES", Decimal("0"))

    def test_reference_currency_is_usd(self) -> None:
        """La moneda de referencia del proyecto es USD (según plan)."""
        assert REFERENCE_CURRENCY == "USD"


class TestToDecimal:
    """Entrada desde JSON (strings) a Decimal seguro."""

    def test_from_string(self) -> None:
        """Convierte '12.345' a Decimal redondeado."""
        assert to_decimal("12.345") == Decimal("12.35")

    def test_from_int(self) -> None:
        """Convierte números enteros."""
        assert to_decimal(10) == Decimal("10.00")

    def test_invalid_raises(self) -> None:
        """Texto no numérico debe lanzar ValueError."""
        with pytest.raises(ValueError):
            to_decimal("no-un-numero")


class TestAmountToMinor:
    """Conversión a la menor unidad (útil para exhibición o métricas)."""

    def test_rounds_correctly(self) -> None:
        """12.34 => 1234; 12.345 => 1235."""
        assert amount_to_minor(Decimal("12.34")) == 1234
        assert amount_to_minor(Decimal("12.345")) == 1235