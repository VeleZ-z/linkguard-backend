"""Cliente asíncrono de reputación de PhishTank (RF-401…405, RF-801/RF-802).

El cliente consulta únicamente el endpoint público configurado en
``PHISHTANK_API_URL``. Nunca contacta la URL ingresada por el usuario, soporta
una ``PHISHTANK_APP_KEY`` opcional y prueba variantes acotadas de la URL antes
de agotar el presupuesto global de 4.0 s (RF-801). Cada consulta se cachea por
separado con clave SHA-256 de la variante (RF-802). Cualquier fallo de red se
degrada a un resultado neutro, de modo que el endpoint siempre responda
HTTP 200.

La respuesta de PhishTank distingue dos estados dentro de su base de datos:

* ``in_database=True`` y ``valid=True`` → coincidencia confirmada
  (``is_match=True``).
* ``in_database=True`` y ``valid=False``/``"Unknown"`` → reporte pendiente de
  verificación por la comunidad (``is_unverified=True``), que el motor de
  scoring penaliza con 15 puntos sin forzar el nivel Alto (Opción B).

**Aislamiento (RNF-101):** las variantes viajan solo como cuerpo POST al host
autorizado; jamás se abre una conexión contra el destino analizado.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Final

import httpx

from app.cache.phishtank_cache import PhishtankCache, get_phishtank_cache
from app.core.config import get_settings
from app.normalization import normalize
from app.schemas import PhishtankStatus

_log = logging.getLogger("linkguard.phishtank")

#: Identificador propio enviado en el encabezado ``User-Agent``.
USER_AGENT: Final[str] = "phishtank/linkguard-api-v1.0"

#: Número máximo de representaciones probadas por URL (RF-801).
MAX_VARIANTS: Final[int] = 4

#: Etiquetas de las variantes, en el mismo orden que :meth:`build_variants`.
VARIANT_LABELS: Final[tuple[str, ...]] = (
    "original_saneada",
    "normalizada",
    "sin_barra_final",
    "con_barra_final",
)

#: Representaciones textuales que PhishTank puede devolver en ``valid``.
_VALID_TRUE: Final[frozenset[str]] = frozenset({"true", "1", "yes", "y", "valid"})
_VALID_FALSE: Final[frozenset[str]] = frozenset(
    {"false", "0", "no", "n", "unknown", "unverified", "pending", "invalid", ""}
)
_CONTROL_CHARS: Final[re.Pattern[str]] = re.compile(r"[\x00-\x1f\x7f]")


@dataclass(frozen=True, slots=True)
class PhishtankResult:
    """Resultado normalizado de una consulta de reputación.

    Attributes:
        is_match: La URL está en la base de datos y fue validada como phishing.
        is_unverified: La URL está reportada, pero su verificación está
            pendiente. Nunca es ``True`` a la vez que ``is_match``.
        status: Estado de la consulta externa.
        variant_index: Índice de la variante que produjo el resultado, o
            ``None`` si no hubo una respuesta definitiva. No forma parte del
            contrato HTTP; sirve para observabilidad y pruebas.
    """

    is_match: bool = False
    is_unverified: bool = False
    status: PhishtankStatus = PhishtankStatus.UNAVAILABLE
    variant_index: int | None = None


class PhishtankClient:
    """Cliente httpx asíncrono con variantes, timeout global y fallback."""

    def __init__(
        self,
        *,
        timeout: float | None = None,
        api_url: str | None = None,
        cache: PhishtankCache | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        app_key: str | None = None,
    ) -> None:
        """Configura el cliente a partir de ``Settings`` o de valores explícitos.

        Args:
            timeout: Presupuesto total en segundos; por defecto
                ``PHISHTANK_TIMEOUT``. Se reparte entre las variantes.
            api_url: Endpoint de consulta; por defecto ``PHISHTANK_API_URL``.
            cache: Caché a usar; por defecto la instancia única del proceso.
            transport: Transporte httpx inyectable para pruebas con ``respx``.
            app_key: Clave opcional; por defecto ``PHISHTANK_APP_KEY``.
        """
        settings = get_settings()
        self._timeout = timeout if timeout is not None else settings.PHISHTANK_TIMEOUT
        self._api_url = api_url or settings.PHISHTANK_API_URL
        self._cache = cache if cache is not None else get_phishtank_cache()
        self._transport = transport
        self._app_key = app_key if app_key is not None else settings.PHISHTANK_APP_KEY

    @staticmethod
    def cache_key(url: str) -> str:
        """Deriva la clave de caché sin retener la URL completa."""
        return hashlib.sha256(url.encode("utf-8")).hexdigest()

    @staticmethod
    def sanitize(url: str) -> str:
        """Quita espacios y caracteres de control sin alterar el destino."""
        return _CONTROL_CHARS.sub("", url).strip()

    @classmethod
    def build_variants(cls, url: str) -> tuple[str, ...]:
        """Devuelve las cuatro variantes normativas en orden (RF-801).

        El orden es: original saneada, normalizada por el motor local, sin
        barra final y con barra final. Puede haber duplicados: :meth:`check_url`
        los descarta antes de consultar. Se usa ``normalize`` con fines de
        comparación léxica; jamás para abrir conexiones contra el destino.
        """
        original = cls.sanitize(url)
        try:
            normalized = normalize(original).normalized_url
        except Exception:
            normalized = original
        sin_barra = normalized.rstrip("/")
        return (
            original,
            normalized,
            sin_barra,
            f"{sin_barra}/",
        )

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

    def _request_data(self, url: str) -> dict[str, str]:
        """Construye el cuerpo POST, incluyendo la clave solo si está definida."""
        data = {"url": url, "format": "json"}
        if self._app_key:
            data["app_key"] = self._app_key
        return data

    async def _query(self, url: str, *, timeout: float | None = None) -> object:
        """Ejecuta una consulta HTTP contra una única variante."""
        async with httpx.AsyncClient(
            timeout=timeout if timeout is not None else self._timeout,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=False,
            transport=self._transport,
        ) as client:
            response = await client.post(self._api_url, data=self._request_data(url))
            response.raise_for_status()
            return response.json()

    async def query_variant(self, url: str, *, timeout: float | None = None) -> tuple[bool, bool]:
        """Consulta una variante concreta sin caché; útil para el laboratorio live.

        No captura excepciones: el script opt-in decide cómo registrar cada
        estado (incluidos los límites de tasa).
        """
        return self._parse_flags(await self._query(url, timeout=timeout))

    @staticmethod
    def _log_variant(index: int, variant: str, status: str) -> None:
        """Registra el estado de una variante sin exponer la URL ni el dominio."""
        etiqueta = VARIANT_LABELS[index] if index < len(VARIANT_LABELS) else f"v{index + 1}"
        _log.info(
            "PHISHTANK_VARIANT label=%s status=%s sha256=%s",
            etiqueta,
            status,
            hashlib.sha256(variant.encode("utf-8")).hexdigest()[:12],
        )

    async def check_url(self, url: str) -> PhishtankResult:
        """Consulta las variantes de ``url`` sin propagar excepciones de red.

        Las variantes se prueban en orden hasta obtener un reporte afirmativo
        (confirmado o pendiente de verificación) o agotar ``PHISHTANK_TIMEOUT``.
        Los negativos —tanto de red como cacheados— no detienen la búsqueda:
        otra variante podría contener el reporte (RF-801).

        Args:
            url: URL normalizada que se desea contrastar con PhishTank.

        Returns:
            ``PhishtankResult`` con ``status`` ``cached``, ``available``,
            ``timeout`` o ``unavailable``. Ante cualquier fallo, ambos flags
            son ``False`` y no se lanza ninguna excepción.
        """
        vistas: set[str] = set()
        variantes: list[str] = []
        for variante in self.build_variants(url):
            if variante and variante not in vistas:
                vistas.add(variante)
                variantes.append(variante)

        deadline = time.monotonic() + self._timeout
        hubo_timeout = False
        hubo_cache_negativa = False
        hubo_respuesta = False
        hubo_fallo_servicio = False

        for indice, variante in enumerate(variantes):
            clave = self.cache_key(variante)
            cacheadas = self._cache.get_flags(clave)
            if cacheadas is not None:
                hubo_cache_negativa = True
                self._log_variant(indice, variante, "cached")
                if cacheadas[0] or cacheadas[1]:
                    return PhishtankResult(
                        is_match=cacheadas[0],
                        is_unverified=cacheadas[1],
                        status=PhishtankStatus.CACHED,
                        variant_index=indice,
                    )
                continue

            restante = deadline - time.monotonic()
            if restante <= 0.0:
                break

            try:
                payload = await self._query(variante, timeout=restante)
                es_match, no_verificado = self._parse_flags(payload)
            except httpx.TimeoutException:
                hubo_timeout = True
                self._log_variant(indice, variante, "timeout")
                continue
            except (httpx.HTTPError, ValueError):
                # Un 4xx/5xx (o un JSON inválido) afecta al servicio, no a la
                # representación de la URL: reintentar variantes solo añadiría
                # carga y podría agravar un límite de tasa.
                hubo_fallo_servicio = True
                self._log_variant(indice, variante, "unavailable")
                break

            self._cache.set(clave, es_match, no_verificado)
            hubo_respuesta = True
            self._log_variant(indice, variante, "available")
            # Un negativo definitivo no descarta las representaciones restantes:
            # RF-801 exige agotar las variantes dentro del presupuesto global.
            if es_match or no_verificado:
                return PhishtankResult(
                    is_match=es_match,
                    is_unverified=no_verificado,
                    status=PhishtankStatus.AVAILABLE,
                    variant_index=indice,
                )

        if hubo_fallo_servicio:
            return PhishtankResult(status=PhishtankStatus.UNAVAILABLE)
        if hubo_timeout:
            return PhishtankResult(status=PhishtankStatus.TIMEOUT)
        if hubo_respuesta:
            return PhishtankResult(status=PhishtankStatus.AVAILABLE)
        if hubo_cache_negativa:
            return PhishtankResult(status=PhishtankStatus.CACHED)
        return PhishtankResult(status=PhishtankStatus.UNAVAILABLE)


@lru_cache
def get_phishtank_client() -> PhishtankClient:
    """Devuelve el cliente único del proceso, con la caché compartida."""
    return PhishtankClient()


def reset_phishtank_client() -> None:
    """Descarta el cliente único; útil en pruebas y reinicios lógicos."""
    get_phishtank_client.cache_clear()


__all__ = [
    "MAX_VARIANTS",
    "USER_AGENT",
    "VARIANT_LABELS",
    "PhishtankClient",
    "PhishtankResult",
    "get_phishtank_client",
    "reset_phishtank_client",
]
