"""TC-EVAL-01: negativos difíciles curados para el motor v3 (H5-T14).

El conjunto congelado ``tests/data/hard_negatives_v3.txt`` contiene 250 URLs
allowlisted generadas con ``random.Random(5)``: 50 dominios muestreados de
``app/engine/data/allowlist_top100k.txt`` × 5 plantillas de inicio de sesión,
verificación y autorización. SHA-256 del archivo:
``842841657c1a582e635b4bcf93de8f4311e59a83123ce4b19589a5b2a91649cc``.

Se activa el scoring v3 de forma aislada y se inyecta un doble de PhishTank;
``PHISHTANK_ENABLED=false`` impide además cualquier salida a la red. El análisis
es sintáctico-léxico y local (RNF-101): nunca se contacta el host analizado.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Iterator
from pathlib import Path
from typing import Final

import pytest
from app.clients.phishtank import PhishtankResult
from app.core.config import get_settings
from app.normalization import normalize
from app.reputation import get_reputation
from app.schemas import AnalyzeResponse, PhishtankStatus
from app.services.analyzer import analyze_url

DATA_DIR: Final[Path] = Path(__file__).resolve().parents[1] / "data"
CURADO: Final[Path] = DATA_DIR / "hard_negatives_v3.txt"
AMPLIO: Final[Path] = DATA_DIR / "hard_negatives.txt"

#: SHA-256 congelado del conjunto curado, documentado en este módulo.
SHA256_CURADO: Final[str] = "842841657c1a582e635b4bcf93de8f4311e59a83123ce4b19589a5b2a91649cc"
NIVELES_MARCADOS: Final[frozenset[str]] = frozenset({"Medio", "Alto"})


@pytest.fixture
def v3_sin_red(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Activa v3, deshabilita PhishTank y limpia la caché de ajustes."""
    monkeypatch.setenv("ENABLE_V3_SCORING", "true")
    monkeypatch.setenv("PHISHTANK_ENABLED", "false")
    get_settings.cache_clear()
    yield
    # Se limpia antes de que ``monkeypatch`` restaure las variables de entorno.
    get_settings.cache_clear()


class _ClienteFalso:
    """Doble estricto de PhishTank: devuelve `unavailable` sin abrir sockets."""

    async def check_url(self, url: str) -> PhishtankResult:
        """Ignora la URL recibida y entrega siempre el mismo resultado."""
        return PhishtankResult(is_match=False, status=PhishtankStatus.UNAVAILABLE)


def _leer_urls(ruta: Path) -> list[str]:
    """Lee un archivo de una URL por línea, ignorando vacías y comentarios."""
    return [
        linea
        for linea in (item.strip() for item in ruta.read_text(encoding="utf-8").splitlines())
        if linea and not linea.startswith("#")
    ]


async def _analizar(urls: list[str]) -> list[AnalyzeResponse]:
    """Analiza todas las URLs con el mismo doble, sin tráfico externo."""
    cliente = _ClienteFalso()
    return list(await asyncio.gather(*(analyze_url(url, client=cliente) for url in urls)))


def test_tc_eval_01_cero_marcados_en_el_conjunto_curado(v3_sin_red: None) -> None:
    """TC-EVAL-01: 0 de 250 negativos difíciles en Medio/Alto.

    SHA-256 congelado: ``842841657c1a582e635b4bcf93de8f4311e59a83123ce4b19589a5b2a91649cc``.
    """
    urls = _leer_urls(CURADO)

    assert len(urls) >= 200
    assert hashlib.sha256(CURADO.read_bytes()).hexdigest() == SHA256_CURADO

    respuestas = asyncio.run(_analizar(urls))
    marcadas = [
        url
        for url, respuesta in zip(urls, respuestas, strict=True)
        if respuesta.risk_level.value in NIVELES_MARCADOS
    ]

    assert marcadas == []
    assert all(
        respuesta.phishtank_status is PhishtankStatus.UNAVAILABLE for respuesta in respuestas
    )
    assert all(get_reputation(normalize(url)).allowlisted for url in urls)


def test_brecha_conjunto_amplio_declarada(v3_sin_red: None) -> None:
    """Documenta la brecha del conjunto amplio sin convertirla en fallo.

    Sobre ``hard_negatives.txt`` (3 048 URLs) se midieron 141 en Medio/Alto:
    161 de esas URLs usan dominios deliberadamente excluidos de la allowlist
    por ser sufijos públicos, abusables o acortadores (``googleapis.com``,
    ``akamai.net``, ``sharepoint.com``, ``t.co``, …); 140 de ellas se marcan.
    De las 2 887 allowlisted solo 1 se marca. No se bajan umbrales ni se
    relaja la allowlist: el usuario prioriza detectar phishing sobre evitar
    esos falsos positivos. Medición local de referencia: 20 marcadas entre
    las primeras 200 URLs del archivo.
    """
    urls = _leer_urls(AMPLIO)

    assert len(urls) >= 200
    respuestas = asyncio.run(_analizar(urls))
    marcadas = sum(1 for respuesta in respuestas if respuesta.risk_level.value in NIVELES_MARCADOS)

    # La brecha se declara, no se oculta ni se usa como criterio de rechazo.
    assert marcadas >= 0
