"""Cliente asíncrono de reputación de PhishTank (RF-401…RF-405, RNF-101).

El cliente consulta únicamente el endpoint público configurado en
``PHISHTANK_API_URL``. Nunca contacta la URL ingresada por el usuario, no usa
claves de API y degrada cualquier fallo de red a un resultado neutro con
``is_match=False``, de modo que el endpoint siempre pueda responder HTTP 200.

La respuesta de PhishTank distingue dos estados dentro de su base de datos:

* ``in_database=True`` y ``valid=True`` → coincidencia confirmada
  (``is_match=True``).
* ``in_database=True`` y ``valid=False``/``"Unknown"`` → reporte pendiente de
  verificación por la comunidad (``is_unverified=True``), que el motor de
  scoring penaliza con 15 puntos sin forzar el nivel Alto (Opción B).
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

#: Representaciones textuales que PhishTank puede devolver en ``valid``.
_VALID_TRUE: Final[frozenset[str]] = frozenset({"true", "1", "yes", "y", "valid"})
_VALID_FALSE: Final[frozenset[str]] = frozenset(
    {"false", "0", "no", "n", "unknown", "unverified", "pending", "invalid", ""}
)


@dataclass(frozen=True, slots=True)
class PhishtankResult:
    """Resultado normalizado de una consulta de reputación.

    Attributes:
        is_match: La URL está en la base de datos y fue validada como phishing.
        is_unverified: La URL está reportada, pero su verificación está
            pendiente. Nunca es ``True`` a la vez que ``is_match``.
        status: Estado de la consulta externa.
    """

    is_match: bool = False
    is_unverified: bool = False
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
    def _is_valid(results: dict[str, object]) -> bool:
        """Interpreta ``valid`` como confirmación, incluyendo ``"Unknown"``.

        PhishTank puede enviar un booleano o una cadena. Cualquier valor no
        reconocido o ``None`` se considera **no validado**: es más seguro
        tratar un reporte dudoso como pendiente que como confirmado.
        """
        value = results.get("valid", True)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in _VALID_TRUE:
                return True
            if normalized in _VALID_FALSE:
                return False
            return False
        if value is None:
            return False
        return bool(value)

    @classmethod
    def _parse_flags(cls, payload: object) -> tuple[bool, bool]:
        """Extrae ``(is_match, is_unverified)`` de la respuesta de PhishTank.

        Raises:
            ValueError: Si el JSON no tiene la estructura esperada.
        """
        if not isinstance(payload, dict):
            raise ValueError("Respuesta de PhishTank con formato inesperado")

        results = payload.get("results")
        if not isinstance(results, dict):
            raise ValueError("Respuesta de PhishTank sin bloque 'results'")

        if not bool(results.get("in_database")):
            return False, False
        if cls._is_valid(results):
            return True, False
        return False, True

    @classmethod
    def _is_match(cls, payload: object) -> bool:
        """Interpreta la respuesta JSON como coincidencia activa confirmada."""
        return cls._parse_flags(payload)[0]

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
            ``timeout`` o ``unavailable``. Ante cualquier fallo, ambos flags
            son ``False`` y no se lanza ninguna excepción.
        """
        key = self.cache_key(url)
        cached = self._cache.get_flags(key)
        if cached is not None:
            is_match, is_unverified = cached
            return PhishtankResult(
                is_match=is_match,
                is_unverified=is_unverified,
                status=PhishtankStatus.CACHED,
            )

        try:
            payload = await self._query(url)
            is_match, is_unverified = self._parse_flags(payload)
        except httpx.TimeoutException:
            return PhishtankResult(status=PhishtankStatus.TIMEOUT)
        except (httpx.HTTPError, ValueError):
            return PhishtankResult(status=PhishtankStatus.UNAVAILABLE)

        self._cache.set(key, is_match, is_unverified)
        return PhishtankResult(
            is_match=is_match,
            is_unverified=is_unverified,
            status=PhishtankStatus.AVAILABLE,
        )


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
