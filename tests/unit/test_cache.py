"""Pruebas unitarias de la caché LRU con TTL (H3-T01, RF-403)."""

from __future__ import annotations

import pytest
from app.cache.phishtank_cache import PhishtankCache
from app.cache.ttl_lru import TTLLRUCache
from app.core.config import get_settings


class _RelojFalso:
    """Reloj monotónico controlable para probar expiraciones sin dormir."""

    def __init__(self) -> None:
        self.ahora = 0.0

    def __call__(self) -> float:
        return self.ahora

    def avanzar(self, segundos: float) -> None:
        self.ahora += segundos


class TestTTLLRUCache:
    """Comportamiento de la estructura genérica."""

    def test_hit_y_miss(self) -> None:
        cache: TTLLRUCache[str, bool] = TTLLRUCache(ttl_seconds=60)

        assert cache.get("ausente") is None
        cache.set("clave", True)

        assert cache.get("clave") is True
        assert "clave" in cache
        assert len(cache) == 1

    def test_expira_por_ttl(self) -> None:
        reloj = _RelojFalso()
        cache: TTLLRUCache[str, int] = TTLLRUCache(ttl_seconds=10, clock=reloj)
        cache.set("clave", 7)

        reloj.avanzar(9.9)
        assert cache.get("clave") == 7

        reloj.avanzar(0.2)
        assert cache.get("clave") is None
        assert len(cache) == 0

    def test_purga_entradas_expiradas(self) -> None:
        reloj = _RelojFalso()
        cache: TTLLRUCache[str, int] = TTLLRUCache(ttl_seconds=10, clock=reloj)
        cache.set("a", 1)
        cache.set("b", 2)

        reloj.avanzar(11)

        assert cache.purge_expired() == 2
        assert len(cache) == 0

    def test_politica_lru_descarta_la_mas_antigua(self) -> None:
        cache: TTLLRUCache[str, int] = TTLLRUCache(ttl_seconds=60, max_entries=2)
        cache.set("a", 1)
        cache.set("b", 2)
        _ = cache.get("a")  # "a" pasa a ser la más reciente
        cache.set("c", 3)

        assert cache.get("b") is None
        assert cache.get("a") == 1
        assert cache.get("c") == 3

    def test_clear(self) -> None:
        cache: TTLLRUCache[str, int] = TTLLRUCache(ttl_seconds=60)
        cache.set("a", 1)

        cache.clear()

        assert len(cache) == 0
        assert cache.get("a") is None

    @pytest.mark.parametrize("ttl", [0, -1])
    def test_rechaza_ttl_invalido(self, ttl: float) -> None:
        with pytest.raises(ValueError, match="TTL"):
            TTLLRUCache(ttl_seconds=ttl)

    def test_rechaza_capacidad_invalida(self) -> None:
        with pytest.raises(ValueError, match="max_entries"):
            TTLLRUCache(ttl_seconds=60, max_entries=0)


class TestPhishtankCache:
    """API específica de PhishTank."""

    def test_get_set_clear(self) -> None:
        cache = PhishtankCache(ttl_seconds=60)

        assert cache.get("hash") is None
        cache.set("hash", True)
        assert cache.get("hash") is True

        cache.clear()
        assert cache.get("hash") is None

    def test_usa_el_ttl_configurado_por_defecto(self) -> None:
        cache = PhishtankCache()

        assert cache._cache._ttl == float(get_settings().PHISHTANK_TTL_SECONDS)

    def test_distingue_falso_de_ausente(self) -> None:
        cache = PhishtankCache(ttl_seconds=60)
        cache.set("hash", False)

        assert cache.get("hash") is False
        assert cache.get("otro") is None


class TestPhishtankCacheInstanciaUnica:
    """Inyección y gestión del singleton de caché."""

    def test_acepta_una_cache_inyectada(self) -> None:
        from app.cache.ttl_lru import TTLLRUCache

        interna: TTLLRUCache[str, bool] = TTLLRUCache(ttl_seconds=60)
        cache = PhishtankCache(cache=interna)
        cache.set("hash", True)

        assert cache.get("hash") is True
        assert len(cache) == 1

    def test_instancia_unica_y_reset(self) -> None:
        from app.cache.phishtank_cache import (
            get_phishtank_cache,
            reset_phishtank_cache,
        )

        reset_phishtank_cache()
        primera = get_phishtank_cache()
        segunda = get_phishtank_cache()
        assert primera is segunda

        reset_phishtank_cache()
        assert get_phishtank_cache() is not primera


class TestTCRF405CachéConsecutiva:
    """TC-RF-405: misma URL dos veces en < 2 h → recuperación inmediata (< 1 ms)
    y status="cached"."""

    def test_segunda_consulta_recuperada_inmediatamente(self) -> None:
        """La caché devuelve el valor sin esperar expiración (TTL 7200 s)."""
        reloj = _RelojFalso()
        cache: TTLLRUCache[str, bool] = TTLLRUCache(ttl_seconds=7200, clock=reloj)

        # Primera consulta: populate.
        cache.set("hash-evil", True)

        import time

        inicio = time.perf_counter()
        valor = cache.get("hash-evil")
        transcurrido_ms = (time.perf_counter() - inicio) * 1000

        assert valor is True
        # Recuperación desde memoria RAM, muy por debajo de 1 ms.
        assert transcurrido_ms < 1.0

    def test_despues_de_7200_segundos_ya_no_esta_cacheada(self) -> None:
        """Tras superar el TTL, la entrada expira y no se considera cached."""
        reloj = _RelojFalso()
        cache: TTLLRUCache[str, bool] = TTLLRUCache(ttl_seconds=7200, clock=reloj)
        cache.set("hash-evil", True)

        reloj.avanzar(7200.1)

        assert cache.get("hash-evil") is None
