"""Caché específica de los resultados de PhishTank (RF-403).

Envuelve :class:`~app.cache.ttl_lru.TTLLRUCache` con la API que consume el
cliente de reputación: la clave es el hash SHA-256 de la URL (para no retener
URLs completas) y el valor es un booleano ``is_phish``. Todo vive en RAM.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Final

from app.cache.ttl_lru import TTLLRUCache
from app.core.config import get_settings

#: Capacidad máxima de la caché de PhishTank.
DEFAULT_MAX_ENTRIES: Final[int] = 4096


class PhishtankCache:
    """Caché RAM de resultados de reputación con TTL configurable."""

    def __init__(
        self,
        ttl_seconds: float | None = None,
        *,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        cache: TTLLRUCache[str, bool] | None = None,
    ) -> None:
        """Inicializa la caché usando el TTL de la configuración si se omite."""
        if cache is not None:
            self._cache = cache
            return

        effective_ttl = (
            float(ttl_seconds)
            if ttl_seconds is not None
            else float(get_settings().PHISHTANK_TTL_SECONDS)
        )
        self._cache = TTLLRUCache[str, bool](effective_ttl, max_entries=max_entries)

    def get(self, url_hash: str) -> bool | None:
        """Devuelve ``is_phish`` cacheado o ``None`` si no hay entrada vigente."""
        return self._cache.get(url_hash)

    def set(self, url_hash: str, is_phish: bool) -> None:
        """Almacena el resultado de reputación para ``url_hash``."""
        self._cache.set(url_hash, is_phish)

    def clear(self) -> None:
        """Vacía la caché completa."""
        self._cache.clear()

    def __len__(self) -> int:
        """Número de entradas retenidas."""
        return len(self._cache)


@lru_cache
def get_phishtank_cache() -> PhishtankCache:
    """Devuelve la instancia única de caché del proceso (RAM)."""
    return PhishtankCache()


def reset_phishtank_cache() -> None:
    """Descarta la instancia única; útil en pruebas y reinicios lógicos."""
    get_phishtank_cache.cache_clear()


__all__ = [
    "DEFAULT_MAX_ENTRIES",
    "PhishtankCache",
    "get_phishtank_cache",
    "reset_phishtank_cache",
]
