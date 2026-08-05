"""currency — Manejo seguro de dinero y monedas.

REGLAS DE ORO (ver riesgos R1/R4 del PLAN):
1. Nunca se usan ``float`` para montos; siempre ``decimal.Decimal`` redondeado
   a 2 decimales (o la precisión adecuada) que a nivel BD es ``NUMERIC``.
2. Toda transacción congelada su conversión a USD (``monto_usd`` + ``tasa_usd``)
   en el momento de registrarse; jamás se recalcula el pasado.
3. La moneda de referencia para reportes es siempre USD.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Final

# ---------------------------------------------------------------------------
# Catálogo de monedas soportadas
# ---------------------------------------------------------------------------

#: Moneda de referencia: todos los reportes se normalizan a USD.
REFERENCE_CURRENCY: Final[str] = "USD"

#: Decimales de redondeo para montos (2 => céntimos / 100).
MONEY_DECIMALS: Final[int] = 2

#: Cantidad mínima representable (0.01) usada en validaciones.
MIN_MONEY: Final[Decimal] = Decimal("0.01")

#: Catálogo de monedas del MVP: código ISO 4217 -> {nombre, símbolo}.
#: Se puede extender sin cambios en la BD (campo texto).
CURRENCIES: Final[dict[str, dict[str, str]]] = {
    "USD": {"nombre": "Dólar estadounidense", "simbolo": "$"},
    "VES": {"nombre": "Bolívar (VES)", "simbolo": "Bs"},
    "EUR": {"nombre": "Euro", "simbolo": "€"},
}

#: Opciones para formularios de DRF (moneda elegible por el usuario).
CURRENCY_CHOICES: Final[list[tuple[str, str]]] = [
    (code, f"{info['simbolo']} — {info['nombre']}") for code, info in CURRENCIES.items()
]


def round_money(value: Decimal) -> Decimal:
    """Redondea un ``Decimal`` a ``MONEY_DECIMALS`` con redondeo "mitad hacia arriba".

    Args:
        value: cantidad (posiblemente con más decimales de los permitidos).

    Returns:
        Cantidad redondeada a 2 decimales, lista para persistir como NUMERIC.
    """
    return value.quantize(Decimal(1).scaleb(-MONEY_DECIMALS), rounding=ROUND_HALF_UP)


def is_valid_amount(value: Decimal) -> bool:
    """Valida que una cantidad sea positiva y con al menos la precisión mínima.

    Args:
        value: cantidad a validar.

    Returns:
        ``True`` si es mayor o igual a 0.01; ``False`` si es 0, negativa o sub-céntimo.
    """
    return isinstance(value, Decimal) and value >= MIN_MONEY


def to_decimal(value: object) -> Decimal:
    """Convierte un valor (str/int/Decimal) a Decimal para montos.

    Args:
        value: valor recibido desde JSON (string) o del modelo.

    Returns:
        ``Decimal`` normalizado a 2 decimales.

    Raises:
        ValueError: si ``value`` no representa un número decimal válido.
    """
    try:
        return round_money(Decimal(str(value)))
    except InvalidOperation as exc:
        raise ValueError(f"{value!r} no es un número decimal válido.") from exc


def amount_to_minor(value: Decimal) -> int:
    """Convierte un monto en unidades principales a la menor unidad (entero).

    Utilidad para logs, métricas o por si algún día se decide mover a enteros.

    Args:
        value: monto en unidades principales (ej. 12.34 -> 1234).

    Returns:
        Entero equivalente en la menor unidad.
    """
    return int(round_money(value) * Decimal(100))


def convert_to_usd(amount: Decimal, currency: str, usd_rate: Decimal) -> Decimal:
    """Convierte una cantidad de la moneda indicada a USD usando una tasa dada.

    Fórmula: ``amount_usd = amount / usd_rate``, donde ``usd_rate`` expresa
    cuántas unidades de ``currency`` valen 1 USD (ej. 752 VES por 1 USD).

    Args:
        amount: cantidad en la moneda original (Decimal).
        currency: código ISO de la moneda original.
        usd_rate: unidades de ``currency`` por 1 USD (Decimal positivo).

    Returns:
        Cantidad equivalente en USD redondeada a 2 decimales.

    Raises:
        ValueError: si ``usd_rate`` no es positivo.
    """
    if currency == REFERENCE_CURRENCY:
        # Si la moneda ya es USD, la conversión es identidad (tasa 1).
        return round_money(amount)
    if usd_rate <= 0:
        raise ValueError("La tasa USD debe ser positiva para convertir.")
    return round_money(amount / usd_rate)


def usd_to_currency(amount_usd: Decimal, currency: str, usd_rate: Decimal) -> Decimal:
    """Convierte una cantidad en USD a la moneda indicada usando una tasa dada.

    Inversa de ``convert_to_usd``: ``amount_currency = amount_usd * usd_rate``.

    Args:
        amount_usd: cantidad en USD (Decimal).
        currency: código ISO de la moneda destino.
        usd_rate: unidades de ``currency`` por 1 USD (Decimal positivo).

    Returns:
        Cantidad equivalente en la moneda destino redondeada a 2 decimales.

    Raises:
        ValueError: si ``usd_rate`` no es positivo.
    """
    if currency == REFERENCE_CURRENCY:
        return round_money(amount_usd)
    if usd_rate <= 0:
        raise ValueError("La tasa USD debe ser positiva para convertir.")
    return round_money(amount_usd * usd_rate)