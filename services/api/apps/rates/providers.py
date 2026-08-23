"""providers — Proveedores de tasas: contrato ``RateProvider`` y DolarApi.

La interfaz permite reemplazar la fuente de tasas sin tocar el resto de la app
(migración de Riesgo R3). El proveedor activo se elige con la variable de
entorno ``RATE_PROVIDER``:
- ``dolarapi``: consulta real a la API pública ``ve.dolarapi.com`` (MIT).
- ``static``: tasa fija, usada en pruebas offline y CI.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

import httpx
from django.conf import settings
from django.utils import timezone


class RateProvider(ABC):
    """Contrato de un proveedor de tasas.

    Cualquier proveedor devuelve una instancia de ``ProviderRate`` con los
    datos normalizados (compra, venta, promedio, rate_date, source).
    """

    @abstractmethod
    def fetch_official_rate(self, currency: str = "VES") -> "ProviderRate":
        """Consulta la tasa oficial actual del USD frente a ``currency``."""

    @abstractmethod
    def fetch_euro_rate(self, currency: str = "VES") -> "ProviderRate":
        """Consulta la tasa oficial actual del EUR frente a ``currency``."""


class ProviderRate:
    """Datos normalizados de una cotización devuelta por un proveedor.

    Atributos:
        source: fuente canónica ("oficial", "paralelo", ...).
        compra / venta / promedio: valores Decimal (pueden ser None).
        rate_date: momento de la cotización (datetime, timezone-aware).
    """

    def __init__(
        self,
        source: str,
        compra=None,
        venta=None,
        promedio=None,
        rate_date: datetime | None = None,
    ) -> None:
        """Inicializa la cotización normalizada."""
        self.source = source
        self.compra = compra
        self.venta = venta
        self.promedio = promedio
        self.rate_date = rate_date or timezone.now()


class RateProviderError(RuntimeError):
    """Lanzada cuando el proveedor no puede obtener una tasa válida."""


class DolarApiProvider(RateProvider):
    """Proveedor que lee la tasa oficial BCV desde ``ve.dolarapi.com``.

    Endpoint: ``GET https://ve.dolarapi.com/v1/dolares/oficial``.
    Respuesta esperada: ``{moneda, fuente, nombre, compra, venta, promedio,
    fechaActualizacion}``.
    """

    BASE_URL = "https://ve.dolarapi.com/v1/dolares/official"
    OFICIAL_URL = "https://ve.dolarapi.com/v1/dolares/oficial"
    EURO_OFICIAL_URL = "https://ve.dolarapi.com/v1/euros/oficial"

    def fetch_official_rate(self, currency: str = "VES") -> ProviderRate:
        """Consulta la tasa Dólar Oficial (BCV) publicada por DolarApi.

        Args:
            currency: moneda local objetivo (el API devuelve VES/USD del BCV).

        Returns:
            ``ProviderRate`` con source='oficial'.

        Raises:
            RateProviderError: si hay error de red, HTTP distinto de 200 o
                el campo ``promedio`` viene vacío.
        """
        try:
            response = httpx.get(self.OFICIAL_URL, timeout=10.0)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as exc:
            raise RateProviderError(f"Error al contactar DolarApi: {exc}") from exc

        if not data.get("promedio"):
            raise RateProviderError("DolarApi no devolvió un promedio válido.")

        return ProviderRate(
            source="oficial",
            compra=data.get("compra"),
            venta=data.get("venta"),
            promedio=data.get("promedio"),
            rate_date=_parse_rate_date(data.get("fechaActualizacion")),
        )

    def fetch_euro_rate(self, currency: str = "VES") -> ProviderRate:
        """Consulta la tasa Euro Oficial (BCV) publicada por DolarApi."""
        try:
            response = httpx.get(self.EURO_OFICIAL_URL, timeout=10.0)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as exc:
            raise RateProviderError(f"Error al contactar DolarApi (Euro): {exc}") from exc

        if not data.get("promedio"):
            raise RateProviderError("DolarApi no devolvió un promedio válido para el euro.")

        return ProviderRate(
            source="oficial",
            compra=data.get("compra"),
            venta=data.get("venta"),
            promedio=data.get("promedio"),
            rate_date=_parse_rate_date(data.get("fechaActualizacion")),
        )


class StaticRateProvider(RateProvider):
    """Proveedor de respaldo con tasa fija (tests / desarrollo sin red).

    Útil para pytest y para que el entorno arranque sin internet.
    """

    def __init__(self, fixed_rate: float = 100.0) -> None:
        """Define la tasa fija que se devolverá siempre.

        Args:
            fixed_rate: unidades de moneda local por 1 USD.
        """
        self.fixed_rate = fixed_rate

    def fetch_official_rate(self, currency: str = "VES") -> ProviderRate:
        """Devuelve la tasa fija configurada como 'oficial'."""
        from decimal import Decimal

        return ProviderRate(source="oficial", promedio=Decimal(str(self.fixed_rate)))

    def fetch_euro_rate(self, currency: str = "VES") -> ProviderRate:
        """Devuelve la tasa fija de euro configurada como 'oficial'."""
        from decimal import Decimal

        return ProviderRate(source="oficial", promedio=Decimal(str(self.fixed_rate * 1.1)))


def get_provider() -> RateProvider:
    """Devuelve el proveedor de tasas activo según ``settings.RATE_PROVIDER``.

    Returns:
        Instancia de ``DolarApiProvider`` o ``StaticRateProvider``.
    """
    provider_name = getattr(settings, "RATE_PROVIDER", "dolarapi")
    if provider_name == "static":
        return StaticRateProvider()
    return DolarApiProvider()


def _parse_rate_date(raw: str | None) -> datetime:
    """Convierte la fecha ISO-8601 de la API a datetime timezone-aware.

    Args:
        raw: cadena tipo ``2026-08-04T00:00:00-04:00`` o None.

    Returns:
        ``datetime`` con zona horaria; si no se puede parsear usa el instante
        actual utc.
    """
    if raw:
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            pass
    from django.utils import timezone

    return timezone.now()