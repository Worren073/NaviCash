"""payment_methods — Métodos de pago del negocio y su moneda/cuenta.

Cada método determina en qué cuenta del negocio entra (cobros) o sale (pagos)
el dinero: los métodos en bolívares van a la cuenta VES y los métodos en
dólares a la cuenta USD. La moneda de la factura/pedido se fija con el método
elegido al crearlo.
"""

from __future__ import annotations

from typing import Final

#: Métodos de pago soportados (código, etiqueta visible).
PAYMENT_METHOD_CHOICES: Final[list[tuple[str, str]]] = [
    ("pago_movil", "Pago Móvil"),
    ("transferencia", "Transferencia bancaria"),
    ("efectivo_ves", "Efectivo (Bs)"),
    ("efectivo_usd", "Efectivo (USD)"),
    ("binance", "Binance"),
    ("zelle", "Zelle"),
]

#: Moneda (y por tanto cuenta del negocio) de cada método de pago.
PAYMENT_METHOD_CURRENCY: Final[dict[str, str]] = {
    "pago_movil": "VES",
    "transferencia": "VES",
    "efectivo_ves": "VES",
    "efectivo_usd": "USD",
    "binance": "USD",
    "zelle": "USD",
}

#: Códigos válidos (para validaciones rápidas).
PAYMENT_METHOD_CODES: Final[tuple[str, ...]] = tuple(PAYMENT_METHOD_CURRENCY)


def method_currency(method: str) -> str:
    """Devuelve la moneda del método de pago (``VES`` o ``USD``)."""
    try:
        return PAYMENT_METHOD_CURRENCY[method]
    except KeyError as exc:  # pragma: no cover - DRF valida antes
        raise ValueError(f"Método de pago desconocido: {method!r}.") from exc
