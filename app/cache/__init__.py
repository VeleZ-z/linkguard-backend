"""Caché volátil en memoria del servicio (RF-403)."""

from __future__ import annotations

from app.cache.phishtank_cache import PhishtankCache, get_phishtank_cache
from app.cache.ttl_lru import TTLLRUCache

__all__ = ["PhishtankCache", "TTLLRUCache", "get_phishtank_cache"]
