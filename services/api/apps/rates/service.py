"""service — Servicio de tasas: consulta con caché, fallback y almacenamiento.

Funciones de alto nivel usadas por el resto del dominio (conversiones de
transacciones) y por el endpoint ``GET /api/rates/current``:
- ``get_current_official_rate(stale_ok=True)``: devuelve la última tasa oficial
  válida, intentando refrescar de la API si la caché supera el TTL.
- ``refresh_official_rate()``: consulta al proveedor y persiste.
- ``get_usd_rate_for_conversion()``: tasa Decimal para conversiones; NUNCA
  devuelve ``Decimal("1")`` como tasa oficial (A6).

Estrategia antifallo (R3 + A5/A6):
1. Si la caché es reciente (< TTL) -> se devuelve tal cual.
2. Si la caché está vieja o no existe -> se intenta refrescar de la API bajo
   un candado atómico (single-flight): solo un worker consulta al proveedor.
3. Si otro worker ya está refrescando -> se devuelve la última persistida,
   aunque esté vencida, sin golpear la red (sin thundering herd).
4. Si la API falla -> se devuelve la última persistida marcada ``is_stale``.
5. Si no hay nada -> ``RateProviderError`` (endpoint 503) y, en
   ``get_usd_rate_for_conversion``, ``BusinessRuleError`` para que el registro
   que convierte se rechace en vez de congelarse con tasa 1 (A6).
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from apps.core.exceptions import BusinessRuleError
from apps.rates.models import ExchangeRate
from apps.rates.providers import RateProviderError, get_provider

#: Candado atómico del refresco (single-flight): clave en la caché compartida.
REFRESH_LOCK_KEY = "rates:refreshing"
#: Duración máxima del candado: si el refresco cuelga, expira y se reintenta.
REFRESH_LOCK_TIMEOUT = 30


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

    Note:
        El single-flight (candado ``cache.add``) se aplica en
        ``get_current_official_rate``, que es el camino de los requests; este
        refresco directo lo usa el comando ``refresh_rates`` (cron).

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

    El refresco es single-flight (A5): ``cache.add`` es el candado atómico que
    asegura que solo un worker consulta al proveedor; si otro request llega
    con el candado activo, se sirve la última fila existente (aunque esté
    vencida) sin golpear la red.

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

    # Single-flight: solo un worker adquiere el candado y refresca.
    if cache.add(REFRESH_LOCK_KEY, 1, REFRESH_LOCK_TIMEOUT):
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
        finally:
            # Se libera el candado al terminar (éxito o error) para no
            # bloquear a otros workers los 30 s completos del timeout.
            cache.delete(REFRESH_LOCK_KEY)

    # El candado ya lo tiene otro worker: servimos la última fila existente
    # (aunque sea vieja) sin golpear al proveedor (sin thundering herd).
    if latest and latest.effective_rate is not None and stale_ok:
        latest.is_stale = True
        latest.save(update_fields=["is_stale"])
        return latest
    raise RateProviderError("Otro proceso está refrescando la tasa oficial; reintenta en unos segundos.")


def get_usd_rate_for_conversion() -> Decimal:
    """Devuelve la tasa Decimal a usar en conversiones de transacciones.

    Simplifica el consumo desde el dominio de transacciones. A6: NUNCA devuelve
    ``Decimal("1")`` como tasa oficial real; si no hay tasa fresca ni caché y
    el proveedor falla, lanza ``BusinessRuleError`` para que el registro que
    convierte sea rechazado y no quede congelado con una tasa falsa.

    Returns:
        Decimal con unidades de moneda local por 1 USD (siempre > 0).

    Raises:
        BusinessRuleError: si la tasa oficial no está disponible.
    """
    try:
        rate = get_current_official_rate(stale_ok=True)
        value = rate.effective_rate
        if value and value > 0:
            return value
    except RateProviderError:
        pass
    raise BusinessRuleError("No pude obtener la tasa oficial del día, intenta en unos minutos")