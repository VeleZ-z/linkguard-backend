"""TC-EVAL-02: guardia de regresión v2 → v3 sobre benchmark congelado (H5-T15).

El archivo ``tests/data/mini_benchmark.tsv`` contiene 400 URLs seleccionadas con
``random.Random(5)`` desde ``data/processed/benchmark.tsv``: 100 JPCERT
estratificadas por año, 100 Phishing.Database, 100 top10k y 100 Citizen Lab.
No incluye negativos difíciles, para no sesgar la medición hacia la allowlist.

SHA-256 congelado del TSV:
``88b5df046ac22c055a0ba3b103439395def9333725459dbe88211e7760fdd71b``.

La comparación se ejecuta en proceso (sin HTTP): ``normalize -> run_rules`` y
``score_results`` para v2, más ``predict -> contributions_by_group ->
get_reputation -> score_v3`` para v3. PhishTank queda deshabilitado y se inyecta
un doble que nunca abre sockets (RNF-101, regla de mocks obligatorios).
"""

from __future__ import annotations

import csv
import hashlib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import pytest
from app.clients.phishtank import PhishtankResult, PhishtankStatus
from app.core.config import get_settings
from app.engine.pipeline import run_rules
from app.ml import contributions_by_group, predict
from app.normalization import normalize
from app.reputation import get_reputation
from app.scoring.calibration import piecewise_linear
from app.scoring.scorer import LOW_MAX, score_results, score_v3

BENCHMARK: Final[Path] = Path(__file__).resolve().parents[1] / "data" / "mini_benchmark.tsv"
CABECERA: Final[tuple[str, ...]] = ("url", "source", "year", "label")
FILAS_ESPERADAS: Final[int] = 400
SHA256_ESPERADO: Final[str] = "88b5df046ac22c055a0ba3b103439395def9333725459dbe88211e7760fdd71b"
UMBRAL_POSITIVO: Final[int] = LOW_MAX + 1
TOLERANCIA: Final[float] = 0.01


@dataclass(frozen=True, slots=True)
class Fila:
    """Fila etiquetada del benchmark congelado."""

    url: str
    label: int
    source: str
    year: str


@pytest.fixture
def v3_activo(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Activa v3 y deshabilita PhishTank, limpiando la caché al salir."""

    monkeypatch.setenv("ENABLE_V3_SCORING", "true")
    monkeypatch.setenv("PHISHTANK_ENABLED", "false")
    get_settings.cache_clear()
    yield
    # ``monkeypatch`` ya restauró las variables: se descarta el objeto cacheado.
    get_settings.cache_clear()


class ClienteFalso:
    """Doble de PhishTank que entrega `unavailable` sin abrir sockets."""

    def __init__(self) -> None:
        """Fija un resultado negativo y determinista."""
        self.resultado = PhishtankResult(
            is_match=False,
            status=PhishtankStatus.UNAVAILABLE,
        )

    async def check_url(self, url: str) -> PhishtankResult:
        """Ignora la URL y devuelve el resultado prefijado."""

        return self.resultado


def leer_benchmark() -> list[Fila]:
    """Verifica cabecera, filas y SHA-256 antes de devolver las filas."""

    contenido = BENCHMARK.read_bytes()
    assert hashlib.sha256(contenido).hexdigest() == SHA256_ESPERADO
    with BENCHMARK.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        assert tuple(reader.fieldnames or ()) == CABECERA
        filas = [
            Fila(
                url=(registro["url"] or "").strip(),
                label=int(registro["label"]),
                source=(registro["source"] or "").strip(),
                year=(registro["year"] or "").strip(),
            )
            for registro in reader
        ]
    assert len(filas) == FILAS_ESPERADAS
    return filas


def medir(filas: list[Fila], *, v3: bool) -> dict[str, int | float]:
    """Calcula TP, FP, FN, TN, recall y FPR con positivo = Medio+Alto."""

    cliente = ClienteFalso()
    tp = fp = fn = tn = 0
    for fila in filas:
        parseada = normalize(fila.url)
        reglas = run_rules(parseada)
        if v3:
            probabilidad = predict(parseada.normalized_url)
            reputacion = get_reputation(parseada)
            desglose = score_v3(
                reglas,
                phishtank_match=cliente.resultado.is_match,
                phishtank_unverified=cliente.resultado.is_unverified,
                s_ml=piecewise_linear(probabilidad),
                allowlisted=reputacion.allowlisted,
                abusable=reputacion.abusable,
                feed_url=reputacion.feed_url,
                feed_host=reputacion.feed_host,
                ml_contributions=contributions_by_group(parseada.normalized_url),
            )
            score = desglose.score
        else:
            score = score_results(
                reglas,
                phishtank_match=cliente.resultado.is_match,
                phishtank_unverified=cliente.resultado.is_unverified,
            ).score
        positivo = score >= UMBRAL_POSITIVO
        if fila.label == 1:
            if positivo:
                tp += 1
            else:
                fn += 1
        elif positivo:
            fp += 1
        else:
            tn += 1
    positivos = tp + fn
    negativos = fp + tn
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "recall": tp / positivos if positivos else 0.0,
        "fpr": fp / negativos if negativos else 0.0,
    }


def test_tc_eval_02_sin_regresion(v3_activo: None) -> None:
    """v3 no baja el recall más de 1 pp ni sube el FPR más de 1 pp."""

    filas = leer_benchmark()
    v2 = medir(filas, v3=False)
    v3 = medir(filas, v3=True)

    # El doble garantiza que ninguna ruta abra sockets hacia PhishTank.
    assert ClienteFalso().resultado.status is PhishtankStatus.UNAVAILABLE
    assert v3["recall"] >= v2["recall"] - TOLERANCIA
    assert v3["fpr"] <= v2["fpr"] + TOLERANCIA
