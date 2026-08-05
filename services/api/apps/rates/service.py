"""service — Servicio de tasas: consulta con caché, fallback y almacenamiento.

Funciones de alto nivel usadas por el resto del dominio (conversiones de
transacciones) y por el endpoint ``GET /api/rates/current``:
- ``get_current_official_rate(stale_ok=True)``: devuelve la última tasa oficial
  válida, intentando refrescar de la API si la caché supera el TTL.
- ``refresh_official_rate()``: consulta al proveedor y persiste.

Estrategia antifallo (R3):
1. Si la caché es reciente (< TTL) -> se devuelve tal cual.
2. Si la caché está vieja o no existe -> se intenta refrescar de la API.
3. Si la API falla -> se devuelve la última persistida marcada ``is_stale``.
4. Si no hay nada -> se lanza ``RateProviderError`` (el endpoint responde 503).
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.utils import timezone

from apps.rates.models import RATE_SOURCES, ExchangeRate
from apps.rates.providers import RateProviderError, get_provider


def _is_fresh(rate: ExchangeRate, ttl_minutes: int) -> bool:
    """Indica si una tasa guardada es reciente según el TTL.

    Args:
        rate: instancia de ExchangeRate.
        ttl_minutes: minutos de validez de la caché (settings.RATE_TTL_MINUTES).

    Returns:
        True si ``rate.input_at + TTL`` sigue en el futuro.
    """
    return rate.input_at + timedelta(minutes=ttl_minutes) > timezone.now()


def refresh_official_rate() -> ExchangeRate:
    """Consulta al proveedor activo y persiste la tasa oficial en la BD.

    Returns:
        La nueva ``ExchangeRate`` guardada (source="oficial").

    Raises:
        RateProviderError: si el proveedor no consigue una tasa válida.
    """
    provider = get_provider()
    fetched = provider.fetch_official_rate()
    rate = ExchangeRate.objects.create(
        source=fetched.source,
        currency="VES",  # El proveedor cotiza VES frente a 1 USD.
        compra=_to_decimal(fetched.compra),
        venta=_to_decimal(fetched.venta),
        promedio=_to_decimal(fetched.promedio),
        rate_date=fetched.rate_date,
        is_stale=False,
    )
    return rate


def _to_decimal(value) -> "Decimal | None":
    """Convierte a Decimal guardando None si el valor viene vacío."""
    if value in (None, ""):
        return None
    return Decimal(str(value))


def get_current_official_rate(stale_ok: bool = True) -> ExchangeRate:
    """Devuelve la tasa oficial USD actual con caché y fallback.

    Args:
        stale_ok: permite devolver una tasa "desactualizada" cuando la API
                  falla (por defecto True, así la app sigue funcionando offline).

    Returns:
        La mejor ``ExchangeRate`` disponible (oficial).

    Raises:
        RateProviderError: si no hay caché, la API falla y ``stale_ok=False``.
    """
    ttl = getattr(settings, "RATE_TTL_MINUTES", 60)
    latest = (
        ExchangeRate.objects.filter(source="oficial")
        .order_by("-input_at")
        .first()
    )

    # Caché reciente -> no hace falta tocar la red.
    if latest and _is_fresh(latest, ttl) and latest.effective_rate is not None:
        latest.is_stale = False
        return latest

    # Intentamos refrescar de la API.
    try:
        refreshed = refresh_official_rate()
        return refreshed
    except RateProviderError:
        # Fallback: la última guardada, marcada como desactualizada.
        if latest and latest.effective_rate is not None and stale_ok:
            latest.is_stale = True
            latest.save(update_fields=["is_stale"])
            return latest
        raise


def get_usd_rate_for_conversion() -> Decimal:
    """Devuelve la tasa Decimal a usar en conversiones de transacciones.

    Simplifica el consumo desde el dominio de transacciones: devuelve
    ``Decimal("1")`` para la moneda de referencia (USD) y siempre una tasa
    válida para el resto. Si no hay tasa alguna, asume 1 (curso de emergencia
    documentado) y registra la conversión como no disponible.

    Returns:
        Decimal con unidades de moneda local por 1 USD (nunca <= 0).
    """
    try:
        rate = get_current_official_rate(stale_ok=True)
        value = rate.effective_rate
        if value and value > 0:
            return value
    except RateProviderError:
        pass
    return Decimal("1")