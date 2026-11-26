"""Pruebas de desempeño del pipeline v3 completo (H5-T14).

- TC-RNF-102-v3: p95 ≤ 50 ms con modelo, reputación local y orquestador reales.
- TC-RNF-104-v3: RAM ≤ 256 MB con los artefactos cargados, medida en un
  proceso hijo aislado para que el RSS de pytest no contamine la medición.

Los dos casos usan el benchmark local y un doble de PhishTank: no hay
peticiones a redes externas ni al host de las URLs analizadas (RNF-101).
Referencias medidas en este entorno: p95 5.57 ms y RSS 205.18 MB.
"""

from __future__ import annotations

import asyncio
import csv
import json
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from time import perf_counter
from typing import Final

import pytest
from app.clients.phishtank import PhishtankResult
from app.core.config import get_settings
from app.ml.model import get_model
from app.reputation import store
from app.schemas import PhishtankStatus
from app.services.analyzer import analyze_url

ROOT: Final[Path] = Path(__file__).resolve().parents[2]
BENCHMARK: Final[Path] = ROOT / "data" / "processed" / "benchmark.tsv"
MAX_P95_MS: Final[float] = 50.0
MAX_RAM_MB: Final[float] = 256.0
MUESTRA: Final[int] = 300
CALENTAMIENTO: Final[int] = 20

#: Programa ejecutado en un proceso limpio para medir ``ru_maxrss`` sin el
#: consumo acumulado de la suite de pytest. Escribe una sola línea JSON.
CODIGO_HIJO: Final[str] = """
import asyncio
import csv
import json
import resource

from app.clients.phishtank import PhishtankResult
from app.ml.model import get_model
from app.reputation import store
from app.schemas import PhishtankStatus
from app.services.analyzer import analyze_url


class ClienteFalso:
    async def check_url(self, url: str) -> PhishtankResult:
        return PhishtankResult(is_match=False, status=PhishtankStatus.UNAVAILABLE)


async def main() -> None:
    modelo = get_model()
    store.load()
    with open("data/processed/benchmark.tsv", encoding="utf-8", newline="") as archivo:
        urls = []
        for fila in csv.DictReader(archivo, delimiter="\\t"):
            url = (fila.get("url") or "").strip()
            if url:
                urls.append(url)
            if len(urls) >= 200:
                break
    cliente = ClienteFalso()
    for url in urls:
        await analyze_url(url, client=cliente)
    print(
        json.dumps(
            {
                "modelo": modelo.available,
                "store": store.loaded,
                "maxrss_mb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
            }
        )
    )


asyncio.run(main())
"""

#: Proceso intermedio ligero: ``ru_maxrss`` se hereda a través de ``execve``,
#: por lo que medir en un hijo directo de pytest contamina la lectura con la
#: RAM acumulada por la suite. El puente nace pequeño y mide a su propio hijo.
CODIGO_PUENTE: Final[str] = """
import os
import subprocess
import sys

resultado = subprocess.run(
    [sys.executable, "-c", os.environ["LG_CODIGO_MEDICION"]],
    capture_output=True,
    text=True,
    check=False,
)
sys.stdout.write(resultado.stdout)
sys.stderr.write(resultado.stderr)
raise SystemExit(resultado.returncode)
"""


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


def _urls_benchmark(limite: int) -> list[str]:
    """Devuelve hasta ``limite`` URLs del TSV local etiquetado."""
    urls: list[str] = []
    with BENCHMARK.open("r", encoding="utf-8", newline="") as archivo:
        for fila in csv.DictReader(archivo, delimiter="\t"):
            url = (fila.get("url") or "").strip()
            if url:
                urls.append(url)
            if len(urls) >= limite:
                break
    return urls


def _percentile(valores: list[float], fraccion: float) -> float:
    """Percentil discreto, idéntico al de ``scripts/ml/evaluate.py``."""
    if not valores:
        return 0.0
    ordenados = sorted(valores)
    indice = min(len(ordenados) - 1, int(round((len(ordenados) - 1) * fraccion)))
    return ordenados[indice]


async def _medir_latencias(urls: list[str]) -> list[float]:
    """Calienta el pipeline y mide ``analyze_url`` una URL por muestra."""
    cliente = _ClienteFalso()
    for url in urls[:CALENTAMIENTO]:
        await analyze_url(url, client=cliente)

    latencias: list[float] = []
    for url in urls:
        inicio = perf_counter()
        await analyze_url(url, client=cliente)
        latencias.append((perf_counter() - inicio) * 1000.0)
    return latencias


def test_p95_menor_50_ms(v3_sin_red: None) -> None:
    """TC-RNF-102-v3: p95 del pipeline v3 completo por debajo de 50 ms."""
    assert get_model().available is True
    store.load()

    urls = _urls_benchmark(MUESTRA)
    assert len(urls) >= 200
    latencias = asyncio.run(_medir_latencias(urls))
    p95 = _percentile(latencias, 0.95)

    assert p95 <= MAX_P95_MS, f"p95 {p95:.2f} ms supera el límite de {MAX_P95_MS:.1f} ms"


def test_ram_con_artefactos_menor_256_mb() -> None:
    """TC-RNF-104-v3: RSS del proceso aislado con artefactos ≤ 256 MB."""
    entorno = dict(os.environ)
    entorno["ENABLE_V3_SCORING"] = "true"
    entorno["PHISHTANK_ENABLED"] = "false"
    entorno["LG_CODIGO_MEDICION"] = CODIGO_HIJO

    # La orden es constante: intérprete del entorno y código fuente fijo.
    resultado = subprocess.run(  # noqa: S603
        [sys.executable, "-c", CODIGO_PUENTE],
        cwd=ROOT,
        env=entorno,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert resultado.returncode == 0, resultado.stderr

    medicion = json.loads(resultado.stdout.strip().splitlines()[-1])
    assert medicion["modelo"] is True
    assert medicion["store"] is True

    maxrss_mb = float(medicion["maxrss_mb"])
    assert maxrss_mb <= MAX_RAM_MB, (
        f"RSS {maxrss_mb:.2f} MB supera el límite de {MAX_RAM_MB:.1f} MB"
    )
