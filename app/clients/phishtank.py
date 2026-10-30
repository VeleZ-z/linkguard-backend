"""Cliente asíncrono de reputación de PhishTank (RF-401…RF-404, RNF-101).

El cliente consulta únicamente el endpoint público configurado en
``PHISHTANK_API_URL``. Nunca contacta la URL ingresada por el usuario, no usa
claves de API y degrada cualquier fallo de red a un resultado neutro con
``is_match=False``, de modo que el endpoint siempre pueda responder HTTP 200.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import lru_cache
from typing import Final

import httpx

from app.cache.phishtank_cache import PhishtankCache, get_phishtank_cache
from app.core.config import get_settings
from app.schemas import PhishtankStatus

#: Identificador propio enviado en el encabezado ``User-Agent``.
USER_AGENT: Final[str] = "phishtank/linkguard-api-v1.0"


@dataclass(frozen=True, slots=True)
class PhishtankResult:
    """Resultado normalizado de una consulta de reputación."""

    is_match: bool = False
    status: PhishtankStatus = PhishtankStatus.UNAVAILABLE


class PhishtankClient:
    """Cliente httpx asíncrono con timeout, caché y fallback silencioso."""

    def __init__(
        self,
        *,
        timeout: float | None = None,
        api_url: str | None = None,
        cache: PhishtankCache | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Configura el cliente a partir de ``Settings`` o de valores explícitos.

        Args:
            timeout: Timeout en segundos; por defecto ``PHISHTANK_TIMEOUT``.
            api_url: Endpoint de consulta; por defecto ``PHISHTANK_API_URL``.
            cache: Caché a usar; por defecto la instancia única del proceso.
            transport: Transporte httpx inyectable para pruebas con ``respx``.
        """
        settings = get_settings()
        self._timeout = timeout if timeout is not None else settings.PHISHTANK_TIMEOUT
        self._api_url = api_url or settings.PHISHTANK_API_URL
        self._cache = cache if cache is not None else get_phishtank_cache()
        self._transport = transport

    @staticmethod
    def cache_key(url: str) -> str:
        """Deriva la clave de caché sin retener la URL completa."""
        return hashlib.sha256(url.encode("utf-8")).hexdigest()

    @staticmethod
    def _is_match(payload: object) -> bool:
        """Interpreta la respuesta JSON de PhishTank como coincidencia activa."""
        if not isinstance(payload, dict):
            raise ValueError("Respuesta de PhishTank con formato inesperado")

        results = payload.get("results")
        if not isinstance(results, dict):
            raise ValueError("Respuesta de PhishTank sin bloque 'results'")

        in_database = bool(results.get("in_database"))
        valid = bool(results.get("valid", True))
        return in_database and valid

    async def _query(self, url: str) -> object:
        """Ejecuta la consulta HTTP y devuelve el JSON decodificado."""
        async with httpx.AsyncClient(
            timeout=self._timeout,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=False,
            transport=self._transport,
        ) as client:
            response = await client.post(
                self._api_url,
                data={"url": url, "format": "json"},
            )
            response.raise_for_status()
            return response.json()

    async def check_url(self, url: str) -> PhishtankResult:
        """Consulta la reputación de ``url`` sin propagar excepciones de red.

        Args:
            url: URL normalizada que se desea contrastar con PhishTank.

        Returns:
            ``PhishtankResult`` con ``status`` ``cached``, ``available``,
            ``timeout`` o ``unavailable``. Ante cualquier fallo, ``is_match``
            es ``False`` y no se lanza ninguna excepción.
        """
        key = self.cache_key(url)
        cached = self._cache.get(key)
        if cached is not None:
            return PhishtankResult(is_match=cached, status=PhishtankStatus.CACHED)

        try:
            payload = await self._query(url)
            is_match = self._is_match(payload)
        except httpx.TimeoutException:
            return PhishtankResult(status=PhishtankStatus.TIMEOUT)
        except (httpx.HTTPError, ValueError):
            return PhishtankResult(status=PhishtankStatus.UNAVAILABLE)

        self._cache.set(key, is_match)
        return PhishtankResult(is_match=is_match, status=PhishtankStatus.AVAILABLE)


@lru_cache
def get_phishtank_client() -> PhishtankClient:
    """Devuelve el cliente único del proceso, con la caché compartida."""
    return PhishtankClient()


def reset_phishtank_client() -> None:
    """Descarta el cliente único; útil en pruebas y reinicios lógicos."""
    get_phishtank_client.cache_clear()


__all__ = [
    "USER_AGENT",
    "PhishtankClient",
    "PhishtankResult",
    "get_phishtank_client",
    "reset_phishtank_client",
]
