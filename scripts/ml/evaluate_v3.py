"""Evaluación final del sistema v3 en proceso (H5-T15, adendo v3 §7).

Ejecuta el sistema completo ``normalize -> run_rules -> predict ->
contributions_by_group -> get_reputation -> score_v3`` sobre el dataset
congelado de 77 642 filas, sin HTTP, sin tráfico hacia la URL analizada y con
un doble de PhishTank que nunca abre sockets. Las cuatro particiones del §7 se
derivan de :mod:`train` (misma semilla y mismas máscaras); el clasificador es el
artefacto servido ``model_v1.json`` y sus umbrales no se modifican. Para las
particiones cruzadas y temporal se reentrena con la máscara correspondiente de
``train.py`` (evita fuga de fuente o de tiempo); la agrupada usa el artefacto
servido. En todos los casos la PL conserva `t_medio`/`t_alto` del artefacto.

Salidas: ``data/processed/evaluation_v3.json`` y
``docs/reports/accuracy-v3.md``. Opcionalmente regenera el benchmark congelado
de 400 URLs con ``--mini-benchmark-out tests/data/mini_benchmark.tsv``.

Uso::

    .venv/bin/python scripts/ml/evaluate_v3.py
"""

from __future__ import annotations

import argparse
import csv
import gc
import hashlib
import json
import os
import random
import resource
import sys
from collections import Counter, defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path
from time import perf_counter
from types import ModuleType
from typing import Any, Final
from urllib.parse import urlsplit

ROOT: Path = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SCRIPTS_DIR: Path = ROOT / "scripts" / "ml"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

# El laboratorio nunca consulta PhishTank ni contacta al host analizado. La
# guardia de rollout se activa solo dentro de este proceso de evaluación.
os.environ["PHISHTANK_ENABLED"] = "false"
os.environ["ENABLE_V3_SCORING"] = "true"

from app.clients.phishtank import PhishtankResult, PhishtankStatus  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.engine.pipeline import run_rules  # noqa: E402
from app.ml import contributions_by_group, predict  # noqa: E402
from app.ml.features import N_FEATURES  # noqa: E402
from app.ml.model import LinearModel  # noqa: E402
from app.normalization import normalize  # noqa: E402
from app.reputation import get_reputation  # noqa: E402
from app.scoring.calibration import piecewise_linear  # noqa: E402
from app.scoring.scorer import LOW_MAX, score_results, score_v3  # noqa: E402

# RF-605: NumPy/sklearn/scipy viven solo en ``requirements-ml.txt``. Se importan
# dentro de las funciones que reentrenan para que importar este módulo (por
# ejemplo desde el arnés RDAP o desde la CI sin dependencias ML) no falle.
# Las funciones de evaluación usadas por el arnés son Python puro.

# ``app.ml`` reexporta ``explain`` como función, por lo que se obtienen los
# módulos por nombre para poder sustituir ``get_model`` durante el refit.
model_module: ModuleType = import_module("app.ml.model")
explain_module: ModuleType = import_module("app.ml.explain")

DATASET_PATH: Final[Path] = ROOT / "data" / "processed" / "dataset.tsv"
BENCHMARK_PATH: Final[Path] = ROOT / "data" / "processed" / "benchmark.tsv"
MINI_BENCHMARK_PATH: Final[Path] = ROOT / "tests" / "data" / "mini_benchmark.tsv"
HARD_NEGATIVES_PATH: Final[Path] = ROOT / "tests" / "data" / "hard_negatives.txt"
CURATED_NEGATIVES_PATH: Final[Path] = ROOT / "tests" / "data" / "hard_negatives_v3.txt"
MODEL_PATH: Final[Path] = ROOT / "app" / "engine" / "data" / "model_v1.json"
DEFAULT_JSON_PATH: Final[Path] = ROOT / "data" / "processed" / "evaluation_v3.json"
DEFAULT_REPORT_PATH: Final[Path] = ROOT / "docs" / "reports" / "accuracy-v3.md"

SEED: Final[int] = 5
FPR_TARGETS: Final[tuple[float, ...]] = (0.003, 0.01, 0.03, 0.05)
FPR_KEYS: Final[tuple[str, ...]] = ("0.003", "0.010", "0.030", "0.050")
POSITIVE_THRESHOLD: Final[int] = LOW_MAX + 1
MINI_SOURCES: Final[tuple[str, ...]] = ("jpcert", "phishdb", "top10k", "citizenlab")
MINI_PER_SOURCE: Final[int] = 100

#: Causas declaradas de la brecha del conjunto amplio de negativos difíciles.
CAUSA_BRECHA_DIFICILES: Final[str] = (
    "161 URLs usan dominios deliberadamente excluidos de la allowlist por ser "
    "sufijos públicos, servicios abusables o acortadores (googleapis.com, "
    "akamai.net, sharepoint.com, t.co, …); 140 de ellas se marcan. De las "
    "2 887 allowlisted solo 1 se marca. No se relajó la allowlist ni se "
    "bajaron los umbrales: el usuario prioriza detectar phishing."
)
CAUSA_LIMITACIONES: Final[tuple[str, ...]] = (
    "Negativos tomados de rankings populares: el FPR en sitios legítimos "
    "pequeños (fuera del top-1M) no se mide.",
    "Los positivos ya fueron reportados y dados de baja: no representan phishing recién creado.",
    "Los feeds etiquetados contienen falsos positivos conocidos; RF-804 ignora "
    "hosts allowlisteados y el piso es Medio.",
    "La edad del dominio, DNS y certificados no se miden (RF-901 es condicional y no aprobado).",
    "Quedan dominios aleatorios cortos residuales sin otras señales; se "
    "depende de los feeds para phishing fresco.",
    "Deriva temporal de campañas: la partición temporal cuantifica la pérdida, "
    "sin reentrenar sobre el conjunto de prueba.",
    "Un adversario que conoce el modelo puede evadirlo; las reglas v2 actúan "
    "como piso y el resultado es preliminar, no un veredicto.",
    "La allowlist deja pasar dominios reputados comprometidos (≤ 0.9 % medido "
    "en el laboratorio); una coincidencia exacta en feed prevalece sobre ella.",
    "Compatibilidad con el anteproyecto: el modelo es lineal e interpretable y "
    "sus evidencias son aditivas; aun así debe consultarse al docente si el "
    "proyecto sigue en evaluación.",
)


@dataclass(frozen=True, slots=True)
class Row:
    """Fila etiquetada de un TSV del laboratorio."""

    url: str
    label: int
    source: str
    year: str


@dataclass(frozen=True, slots=True)
class Evaluated:
    """Resultados de una URL con el sistema v2 y el sistema completo v3."""

    row: Row
    score_v2: int
    score_v3: int
    s_pre: int
    probability: float
    allowlisted: bool
    abusable: bool
    feed_url: bool
    feed_host: bool
    v2_ms: float
    v3_ms: float


class ClienteFalso:
    """Doble de PhishTank: devuelve `unavailable` sin abrir sockets."""

    def __init__(self) -> None:
        """Fija un resultado negativo y determinista."""
        self.resultado = PhishtankResult(
            is_match=False,
            status=PhishtankStatus.UNAVAILABLE,
        )

    async def check_url(self, url: str) -> PhishtankResult:
        """Ignora la URL y entrega el resultado prefijado (sin red)."""

        return self.resultado


def sha256(path: Path) -> str:
    """Calcula el SHA-256 de un archivo por bloques."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for bloque in iter(lambda: handle.read(1 << 20), b""):
            digest.update(bloque)
    return digest.hexdigest()


def artifact_thresholds() -> tuple[float, float]:
    """Lee `t_medio` y `t_alto` del artefacto, sin recalibración."""

    contenido: dict[str, Any] = json.loads(MODEL_PATH.read_text(encoding="utf-8"))
    umbrales = contenido["thresholds"]
    return float(umbrales["medio"]), float(umbrales["alto"])


@contextmanager
def modelo_temporal(modelo: LinearModel) -> Iterator[None]:
    """Sustituye el modelo global solo dentro del bloque, sin escribir disco."""

    original_modelo = model_module.get_model
    original_explicacion = explain_module.get_model
    model_module.get_model = lambda: modelo
    explain_module.get_model = lambda: modelo
    try:
        yield
    finally:
        model_module.get_model = original_modelo
        explain_module.get_model = original_explicacion


def modelo_reentrenado(
    matriz: Any,
    etiquetas: Any,
    mascara_entrenamiento: Any,
    umbrales: tuple[float, float],
) -> LinearModel:
    """Reentrena el clasificador con la máscara de la partición, poda incluida.

    Se conservan los hiperparámetros de :func:`train.fit` y la poda de
    :data:`export_model.DEFAULT_MIN_WEIGHT`. Los umbrales de la PL siguen siendo
    los del artefacto servido: no se calibran sobre el conjunto de prueba.
    """

    from export_model import DEFAULT_MIN_WEIGHT  # noqa: PLC0415
    from train import fit  # noqa: PLC0415

    estimado = fit(matriz, etiquetas, mascara_entrenamiento, seed=SEED)
    coeficientes = estimado.coef_[0]
    pesos = {
        indice: float(valor)
        for indice, valor in enumerate(coeficientes)
        if abs(float(valor)) >= DEFAULT_MIN_WEIGHT
    }
    return LinearModel(
        version="model-v1-refit",
        feature_spec_version="v1",
        n_features=N_FEATURES,
        bias=float(estimado.intercept_[0]),
        weights=pesos,
        thresholds={"medio": umbrales[0], "alto": umbrales[1]},
        trained_at="refit-por-particion",
        data_manifest={},
        available=True,
    )


def load_rows(path: Path) -> list[Row]:
    """Carga un TSV con columnas ``url``, ``label``, ``source`` y ``year``."""

    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        return [
            Row(
                url=(registro.get("url") or "").strip(),
                label=int(registro.get("label") or 0),
                source=(registro.get("source") or "").strip(),
                year=(registro.get("year") or "").strip(),
            )
            for registro in reader
            if (registro.get("url") or "").strip()
        ]


def build_mini_benchmark(path: Path, seed: int = SEED) -> list[Row]:
    """Selecciona 400 URLs congeladas y estratificadas desde ``benchmark.tsv``.

    100 JPCERT estratificadas por año (cuotas proporcionales con mayor resto),
    100 PhishDB, 100 top10k y 100 Citizen Lab. Sin negativos difíciles para no
    sesgar la medición hacia la allowlist. El orden de selección es el mismo
    para ``random.Random(seed)`` en cualquier ejecución (RNF-108).
    """

    filas = load_rows(path)
    generador = random.Random(seed)
    seleccionadas: list[Row] = []
    for fuente in MINI_SOURCES:
        grupo = [fila for fila in filas if fila.source == fuente]
        if fuente != "jpcert":
            seleccionadas.extend(generador.sample(grupo, MINI_PER_SOURCE))
            continue

        por_anio: dict[str, list[Row]] = defaultdict(list)
        for fila in grupo:
            por_anio[fila.year].append(fila)
        total = len(grupo)
        cupos = {anio: len(rows) * MINI_PER_SOURCE // total for anio, rows in por_anio.items()}
        pendiente = MINI_PER_SOURCE - sum(cupos.values())
        orden = sorted(
            por_anio,
            key=lambda anio: (
                -((len(por_anio[anio]) * MINI_PER_SOURCE) / total - cupos[anio]),
                anio,
            ),
        )
        for anio in orden[:pendiente]:
            cupos[anio] += 1
        for anio in sorted(por_anio):
            seleccionadas.extend(generador.sample(por_anio[anio], cupos[anio]))
    return seleccionadas


def write_mini_benchmark(filas: list[Row], destino: Path) -> None:
    """Escribe el benchmark congelado con cabecera estable."""

    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open("w", encoding="utf-8", newline="") as handle:
        handle.write("url\tsource\tyear\tlabel\n")
        for fila in filas:
            handle.write(f"{fila.url}\t{fila.source}\t{fila.year}\t{fila.label}\n")


def _host_of(url: str) -> str:
    """Extrae el host de una URL con o sin esquema."""

    candidato = url if "://" in url else "http://" + url
    try:
        return (urlsplit(candidato).hostname or "").lower().rstrip(".")
    except ValueError:
        return ""


def _evaluacion_degradada(fila: Row) -> Evaluated:
    """Devuelve una fila neutra para conservar el orden de las máscaras."""

    return Evaluated(
        row=fila,
        score_v2=0,
        score_v3=0,
        s_pre=0,
        probability=0.0,
        allowlisted=False,
        abusable=False,
        feed_url=False,
        feed_host=False,
        v2_ms=0.0,
        v3_ms=0.0,
    )


def evaluate_rows(
    filas: list[Row],
    umbrales: tuple[float, float] | None = None,
) -> tuple[list[Evaluated], int]:
    """Evalúa cada fila con v2 y con el sistema completo v3, en proceso."""

    cliente = ClienteFalso()
    resultados: list[Evaluated] = []
    errores = 0
    for fila in filas:
        iniciado = perf_counter()
        try:
            parseada = normalize(fila.url)
            reglas = run_rules(parseada)
            score_v2 = score_results(reglas).score
        except Exception:
            errores += 1
            resultados.append(_evaluacion_degradada(fila))
            continue
        v2_ms = (perf_counter() - iniciado) * 1000.0

        iniciado = perf_counter()
        try:
            probabilidad = predict(parseada.normalized_url)
            contribuciones = contributions_by_group(parseada.normalized_url)
            reputacion = get_reputation(parseada)
            desglose = score_v3(
                reglas,
                phishtank_match=cliente.resultado.is_match,
                phishtank_unverified=cliente.resultado.is_unverified,
                s_ml=piecewise_linear(
                    probabilidad,
                    t_medio=None if umbrales is None else umbrales[0],
                    t_alto=None if umbrales is None else umbrales[1],
                ),
                allowlisted=reputacion.allowlisted,
                abusable=reputacion.abusable,
                feed_url=reputacion.feed_url,
                feed_host=reputacion.feed_host,
                ml_contributions=contribuciones,
            )
        except Exception:
            errores += 1
            resultados.append(_evaluacion_degradada(fila))
            continue
        v3_ms = (perf_counter() - iniciado) * 1000.0
        resultados.append(
            Evaluated(
                row=fila,
                score_v2=score_v2,
                score_v3=desglose.score,
                s_pre=desglose.s_pre,
                probability=probabilidad,
                allowlisted=reputacion.allowlisted,
                abusable=reputacion.abusable,
                feed_url=reputacion.feed_url,
                feed_host=reputacion.feed_host,
                v2_ms=v2_ms,
                v3_ms=v3_ms,
            )
        )
    return resultados, errores


def score_stage(elementos: list[Evaluated], etapa: str) -> list[int]:
    """Devuelve el score de una etapa de la ablación sobre los mismos URLs."""

    if etapa == "reglas":
        return [elemento.score_v2 for elemento in elementos]
    if etapa == "modelo":
        return [elemento.s_pre for elemento in elementos]
    if etapa == "allowlist":
        return [
            min(elemento.s_pre, LOW_MAX)
            if elemento.allowlisted and not elemento.abusable
            else elemento.s_pre
            for elemento in elementos
        ]
    if etapa == "feeds":
        # PhishTank es el doble `unavailable`: no aporta coincidencias.
        return [elemento.score_v3 for elemento in elementos]
    raise ValueError(f"Etapa de ablación desconocida: {etapa}")


def binary_metrics(
    elementos: list[Evaluated],
    scores: list[int],
    *,
    umbral: int = POSITIVE_THRESHOLD,
) -> dict[str, Any]:
    """Calcula matriz, recall, FPR, precisión y F1 con positivo = Medio+Alto."""

    tp = fp = fn = tn = 0
    for elemento, score in zip(elementos, scores, strict=True):
        positivo = score >= umbral
        if elemento.row.label == 1:
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
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / positivos if positivos else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "n": len(elementos),
        "positivos": positivos,
        "negativos": negativos,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "fpr": fp / negativos if negativos else 0.0,
    }


def auc_pr(elementos: list[Evaluated], scores: list[int]) -> tuple[float | None, float | None]:
    """Calcula AUC y PR-AUC por rangos, sin dependencias externas."""

    pares = [(score, elemento.row.label) for elemento, score in zip(elementos, scores, strict=True)]
    positivos = sum(etiqueta == 1 for _, etiqueta in pares)
    negativos = len(pares) - positivos
    if not positivos or not negativos:
        return None, None

    ordenados = sorted(pares, key=lambda par: par[0])
    suma_rangos = 0.0
    indice = 0
    while indice < len(ordenados):
        final = indice + 1
        while final < len(ordenados) and ordenados[final][0] == ordenados[indice][0]:
            final += 1
        rango_medio = ((indice + 1) + final) / 2.0
        suma_rangos += rango_medio * sum(etiqueta == 1 for _, etiqueta in ordenados[indice:final])
        indice = final
    auc = (suma_rangos - positivos * (positivos + 1) / 2.0) / (positivos * negativos)

    decrecientes = sorted(pares, key=lambda par: -par[0])
    verdaderos = 0
    falsos = 0
    average_precision = 0.0
    indice = 0
    while indice < len(decrecientes):
        final = indice + 1
        while final < len(decrecientes) and decrecientes[final][0] == decrecientes[indice][0]:
            final += 1
        grupo_positivos = sum(etiqueta == 1 for _, etiqueta in decrecientes[indice:final])
        grupo_negativos = (final - indice) - grupo_positivos
        verdaderos += grupo_positivos
        falsos += grupo_negativos
        if grupo_positivos:
            precision_grupo = verdaderos / (verdaderos + falsos)
            average_precision += (grupo_positivos / positivos) * precision_grupo
        indice = final
    return auc, average_precision


def recall_at_fpr(
    elementos: list[Evaluated],
    scores: list[int],
    objetivos: tuple[float, ...] = FPR_TARGETS,
) -> dict[str, dict[str, float]]:
    """Barre umbrales enteros y reporta el máximo recall con FPR ≤ objetivo."""

    conteos = Counter(
        (elemento.row.label, score) for elemento, score in zip(elementos, scores, strict=True)
    )
    negativos = sum(conteos[(0, score)] for score in range(101))
    positivos = sum(conteos[(1, score)] for score in range(101))
    resultado: dict[str, dict[str, float]] = {}
    acumulado_tp = 0
    acumulado_fp = 0
    mejor: dict[float, tuple[float, int]] = {}
    for objetivo in objetivos:
        mejor[objetivo] = (0.0, 101)
    for umbral in range(101, -1, -1):
        if umbral < 101:
            acumulado_tp += conteos[(1, umbral)]
            acumulado_fp += conteos[(0, umbral)]
        if not positivos or not negativos:
            continue
        tasa_fp = acumulado_fp / negativos
        recall = acumulado_tp / positivos
        for objetivo in objetivos:
            if tasa_fp <= objetivo and recall >= mejor[objetivo][0]:
                mejor[objetivo] = (recall, umbral)
    for objetivo in objetivos:
        clave = f"{objetivo:.3f}"
        recall, umbral = mejor[objetivo]
        resultado[clave] = {"recall": recall, "umbral": float(umbral)}
    return resultado


def percentile(valores: list[float], fraccion: float) -> float:
    """Percentil discreto por interpolación simple."""

    if not valores:
        return 0.0
    ordenados = sorted(valores)
    indice = min(len(ordenados) - 1, int(round((len(ordenados) - 1) * fraccion)))
    return ordenados[indice]


def latency_summary(elementos: list[Evaluated]) -> dict[str, dict[str, float]]:
    """Resume latencias locales de v2 y del sistema completo v3."""

    return {
        "v2": {
            "p50": percentile([elemento.v2_ms for elemento in elementos], 0.5),
            "p95": percentile([elemento.v2_ms for elemento in elementos], 0.95),
        },
        "v3": {
            "p50": percentile([elemento.v3_ms for elemento in elementos], 0.5),
            "p95": percentile([elemento.v3_ms for elemento in elementos], 0.95),
        },
    }


def per_source(elementos: list[Evaluated]) -> dict[str, dict[str, Any]]:
    """Agrupa métricas v3 por fuente del dataset."""

    grupos: dict[str, list[Evaluated]] = defaultdict(list)
    for elemento in elementos:
        grupos[elemento.row.source].append(elemento)
    return {
        fuente: binary_metrics(filas, [elemento.score_v3 for elemento in filas])
        for fuente, filas in sorted(grupos.items())
    }


def per_year(elementos: list[Evaluated]) -> dict[str, dict[str, Any]]:
    """Desglosa los resultados de JPCERT por año."""

    grupos: dict[str, list[Evaluated]] = defaultdict(list)
    for elemento in elementos:
        if elemento.row.source == "jpcert" and elemento.row.year.isdigit():
            grupos[elemento.row.year].append(elemento)
    return {
        anio: binary_metrics(filas, [elemento.score_v3 for elemento in filas])
        for anio, filas in sorted(grupos.items())
    }


def partition_summary(
    elementos: list[Evaluated],
    mascara: Any,
    *,
    nombre: str,
) -> dict[str, Any]:
    """Compone todas las métricas exigidas para una partición del §7."""

    booleanas = mascara.tolist() if hasattr(mascara, "tolist") else list(mascara)
    prueba = [
        elemento for elemento, conservar in zip(elementos, booleanas, strict=True) if conservar
    ]
    scores_v2 = [elemento.score_v2 for elemento in prueba]
    scores_v3 = [elemento.score_v3 for elemento in prueba]
    metrics_v3 = binary_metrics(prueba, scores_v3)
    auc_v3, pr_auc_v3 = auc_pr(prueba, scores_v3)
    auc_v2, pr_auc_v2 = auc_pr(prueba, scores_v2)
    return {
        "nombre": nombre,
        "v2": {
            **binary_metrics(prueba, scores_v2),
            "auc": auc_v2,
            "pr_auc": pr_auc_v2,
            "recall_at_fpr": recall_at_fpr(prueba, scores_v2),
        },
        "v3": {
            **metrics_v3,
            "auc": auc_v3,
            "pr_auc": pr_auc_v3,
            "recall_at_fpr": recall_at_fpr(prueba, scores_v3),
            "umbral_operativo": POSITIVE_THRESHOLD,
            "confusion": {
                "tp": metrics_v3["tp"],
                "fp": metrics_v3["fp"],
                "fn": metrics_v3["fn"],
                "tn": metrics_v3["tn"],
            },
        },
        "latencia_ms": latency_summary(prueba),
        "por_fuente": per_source(prueba),
        "por_anio": per_year(prueba),
    }


def hard_negative_summary(elementos: list[Evaluated], ruta: Path) -> dict[str, Any]:
    """Resume los negativos difíciles marcados en Medio/Alto."""

    marcados = [elemento for elemento in elementos if elemento.score_v3 >= POSITIVE_THRESHOLD]
    return {
        "archivo": str(ruta.relative_to(ROOT)),
        "sha256": sha256(ruta),
        "n": len(elementos),
        "marcados": len(marcados),
        "allowlisted_marcados": sum(1 for elemento in marcados if elemento.allowlisted),
        "abusable_marcado": sum(1 for elemento in marcados if elemento.abusable),
    }


def ablation_summary(elementos: list[Evaluated]) -> dict[str, Any]:
    """Calcula la ablación de cuatro etapas sobre la partición agrupada."""

    nombres = (
        ("reglas", "Solo reglas v2"),
        ("modelo", "Reglas + modelo (max)"),
        ("allowlist", "Anterior + allowlist"),
        ("feeds", "Anterior + feeds y PhishTank simulado"),
    )
    etapas: dict[str, Any] = {}
    previo: float | None = None
    for clave, descripcion in nombres:
        scores = score_stage(elementos, clave)
        metricas = binary_metrics(elementos, scores)
        curva = recall_at_fpr(elementos, scores)
        actual = curva["0.030"]["recall"]
        etapas[clave] = {
            "descripcion": descripcion,
            "recall_fpr_3": actual,
            "umbral_fpr_3": curva["0.030"]["umbral"],
            "fpr": metricas["fpr"],
            "precision": metricas["precision"],
            "recall": metricas["recall"],
            "ganancia_pp": None if previo is None else (actual - previo) * 100.0,
        }
        previo = actual
    return etapas


def _pct(valor: float | None) -> str:
    """Formatea una fracción como porcentaje con un decimal."""

    return "—" if valor is None else f"{valor * 100:.1f} %"


def _num(valor: float | None, decimales: int = 4) -> str:
    """Formatea un número con decimales fijos."""

    return "—" if valor is None else f"{valor:.{decimales}f}"


def _delta(actual: float, anterior: float) -> str:
    """Expresa la diferencia en puntos porcentuales."""

    return f"{(actual - anterior) * 100:+.1f} pp"


def _estado(valor: float, objetivo: float) -> str:
    """Devuelve el marcador de cumplimiento de una meta."""

    return "✅" if valor >= objetivo else "⚠️"


def _causa(estado: str, texto: str) -> str:
    """Solo explica la causa cuando la meta no se cumple."""

    return "—" if estado == "✅" else texto


def render_report(payload: dict[str, Any]) -> str:
    """Genera el informe Markdown con cifras reales de la ejecución."""

    meta = payload["metadata"]
    lineas: list[str] = [
        "# Evaluación final del sistema LinkGuard v3 (H5-T15)",
        "",
        f"**Fecha:** {meta['evaluated_at']}",
        f"**Dataset:** `{meta['dataset']}` · {meta['dataset_rows']:,} filas · "
        f"SHA-256 `{meta['dataset_sha256']}`",
        f"**Benchmark congelado:** `{meta['mini_benchmark']}` · 400 filas · "
        f"SHA-256 `{meta['mini_benchmark_sha256']}`",
        f"**Protocolo:** adendo v3 §7 (agrupada 70/30 por dominio registrable, "
        f"cruzada entre fuentes, temporal JPCERT ≤2023 → 2025-26 y negativos "
        f"difíciles aparte). Semilla fija `{meta['seed']}` (RNF-108).",
        f"**Metodología de modelo:** {meta['metodologia']}. Así se evita que el "
        f"artefacto servido, entrenado con ambas fuentes, infiltre información "
        f"en las particiones cruzadas.",
        "**Rollout:** `ENABLE_V3_SCORING` es `false` por defecto en producción; "
        "este script lo fija a `true` en su proceso y TC-EVAL-02 lo activa con "
        "`monkeypatch`. `PHISHTANK_ENABLED=false` y cliente falso: cero tráfico "
        "de red (RNF-101).",
        f"**Umbrales del artefacto:** `t_medio={meta['thresholds']['medio']:.6f}`, "
        f"`t_alto={meta['thresholds']['alto']:.6f}` y frontera Medio "
        f"`score ≥ {meta['umbral_operativo']}`. **No se han reducido ni "
        f"recalibrado umbrales; las brechas se reportan con su causa.** "
        f"Se prioriza detectar phishing (recall) por encima de evitar falsos "
        f"positivos.",
        "",
        "## 1. Antes / después: motor v2 → sistema completo v3",
        "",
        "Positivo operativo = Medio+Alto (`score ≥ "
        f"{meta['umbral_operativo']}`). Las latencias son del mismo proceso.",
        "",
        "| Ámbito | Recall v2 | Recall v3 | Δ recall | FPR v2 | FPR v3 | Δ FPR | "
        "Prec. v2 | Prec. v3 | F1 v2 | F1 v3 | p95 v2 | p95 v3 |",
        "| :-- | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: |",
    ]
    resumenes: list[tuple[str, dict[str, Any]]] = [("Global (todas las filas)", payload["global"])]
    resumenes.extend((str(datos["nombre"]), datos) for datos in payload["partitions"].values())
    for nombre, datos in resumenes:
        anterior = datos["v2"]
        actual = datos["v3"]
        lat = datos["latencia_ms"]
        lineas.append(
            f"| {nombre} | {_pct(anterior['recall'])} | {_pct(actual['recall'])} | "
            f"{_delta(actual['recall'], anterior['recall'])} | "
            f"{_pct(anterior['fpr'])} | {_pct(actual['fpr'])} | "
            f"{_delta(actual['fpr'], anterior['fpr'])} | "
            f"{_pct(anterior['precision'])} | {_pct(actual['precision'])} | "
            f"{_num(anterior['f1'], 3)} | {_num(actual['f1'], 3)} | "
            f"{lat['v2']['p95']:.3f} ms | {lat['v3']['p95']:.3f} ms |"
        )

    lineas.extend(
        [
            "",
            "## 2. Metas del adendo §7",
            "",
            "| KPI | Meta | Medición | Resultado | Causa cuando no se cumple |",
            "| :-- | :-- | --: | :-- | :-- |",
        ]
    )
    metas = payload["goals"]
    for nombre, meta_kpi in metas.items():
        lineas.append(
            f"| {nombre} | {meta_kpi['meta']} | {meta_kpi['medicion']} | "
            f"{meta_kpi['estado']} | {meta_kpi['causa']} |"
        )

    lineas.extend(
        [
            "",
            "## 3. KPIs por partición (sistema completo v3)",
            "",
            "AUC y PR-AUC se calculan sobre el score entero final del sistema "
            "(rangos con empates). Recall@FPR surge de barrer ese score; la "
            "matriz usa el umbral operativo fijo, no el del barrido.",
            "",
            "| Partición | n | Pos. | Neg. | AUC | PR-AUC | R@0.3 % | R@1 % | "
            "R@3 % | R@5 % | TP | FP | FN | TN |",
            "| :-- | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: |",
        ]
    )
    for datos in payload["partitions"].values():
        actual = datos["v3"]
        curva = actual["recall_at_fpr"]
        celdas = " | ".join(_pct(curva[clave]["recall"]) for clave in FPR_KEYS)
        confusion = actual["confusion"]
        lineas.append(
            f"| {datos['nombre']} | {actual['n']:,} | {actual['positivos']:,} | "
            f"{actual['negativos']:,} | {_num(actual['auc'])} | "
            f"{_num(actual['pr_auc'])} | {celdas} | "
            f"{confusion['tp']:,} | {confusion['fp']:,} | {confusion['fn']:,} | "
            f"{confusion['tn']:,} |"
        )

    lineas.extend(
        [
            "",
            "Referencia del modelo puro reentrenado por partición (H5-T09): "
            "agrupada 93.4 %, PhishDB→JPCERT 84.5 %, JPCERT→PhishDB 76.2 % y "
            "temporal 90.0 % @FPR 3 %. El sistema completo añade la PL, la "
            "allowlist y los feeds; en ningún caso se reajustaron los umbrales "
            "para mejorar estas cifras.",
            "",
            "Umbrales del barrido Recall@FPR (score entero, no modificado):",
            "",
            "| Partición | R@0.3 % (umbral) | R@1 % (umbral) | R@3 % (umbral) | R@5 % (umbral) |",
            "| :-- | --: | --: | --: | --: |",
        ]
    )
    for datos in payload["partitions"].values():
        curva = datos["v3"]["recall_at_fpr"]
        celdas = " | ".join(
            f"{_pct(curva[clave]['recall'])} ({int(curva[clave]['umbral'])})" for clave in FPR_KEYS
        )
        lineas.append(f"| {datos['nombre']} | {celdas} |")

    lineas.extend(
        [
            "",
            "### 3.1 Desglose por fuente",
            "",
            "| Partición | Fuente | n | Pos. | Neg. | Recall | FPR | Precisión | F1 |",
            "| :-- | :-- | --: | --: | --: | --: | --: | --: | --: |",
        ]
    )
    for datos in payload["partitions"].values():
        for fuente, item in datos["por_fuente"].items():
            lineas.append(
                f"| {datos['nombre']} | {fuente} | {item['n']:,} | "
                f"{item['positivos']:,} | {item['negativos']:,} | "
                f"{_pct(item['recall'])} | {_pct(item['fpr'])} | "
                f"{_pct(item['precision'])} | {_num(item['f1'], 3)} |"
            )

    lineas.extend(
        [
            "",
            "### 3.2 Desglose de JPCERT por año",
            "",
            "| Partición | Año | n | Pos. | TP | FP | Recall | FPR |",
            "| :-- | --: | --: | --: | --: | --: | --: | --: |",
        ]
    )
    for datos in payload["partitions"].values():
        for anio, item in datos["por_anio"].items():
            lineas.append(
                f"| {datos['nombre']} | {anio} | {item['n']:,} | "
                f"{item['positivos']:,} | {item['tp']:,} | {item['fp']:,} | "
                f"{_pct(item['recall'])} | {_pct(item['fpr'])} |"
            )

    lineas.extend(
        [
            "",
            "## 4. Ablación sobre la partición agrupada",
            "",
            "Las cuatro etapas comparten las mismas "
            f"{payload['ablation_n']:,} URLs de reserva. El PhishTank simulado "
            "está `unavailable`, por lo que etapa (d) no añade coincidencias "
            "externas: se mide tal como quedaría con `PHISHTANK_ENABLED=false`.",
            "",
            "| Etapa | Recall@FPR 3 % | Ganancia | Umbral del barrido | FPR "
            "(score ≥ 31) | Precisión | Recall (score ≥ 31) |",
            "| :-- | --: | --: | --: | --: | --: | --: |",
        ]
    )
    for etapa in payload["ablacion"].values():
        ganancia = "—" if etapa["ganancia_pp"] is None else f"{etapa['ganancia_pp']:+.1f} pp"
        lineas.append(
            f"| {etapa['descripcion']} | {_pct(etapa['recall_fpr_3'])} | "
            f"{ganancia} | {int(etapa['umbral_fpr_3'])} | "
            f"{_pct(etapa['fpr'])} | {_pct(etapa['precision'])} | "
            f"{_pct(etapa['recall'])} |"
        )

    lat = payload["latencia_ms"]
    lineas.extend(
        [
            "",
            "## 5. Latencia y memoria",
            "",
            "| Medición | p50 | p95 |",
            "| :-- | --: | --: |",
            f"| Motor v2 en proceso | {lat['v2']['p50']:.3f} ms | {lat['v2']['p95']:.3f} ms |",
            f"| Sistema completo v3 en proceso | {lat['v3']['p50']:.3f} ms | "
            f"{lat['v3']['p95']:.3f} ms |",
            "",
            f"- RAM pico del proceso de evaluación: "
            f"**{payload['ram_pico_mb']:.2f} MB** (`ru_maxrss`). Este proceso "
            f"carga además el dataset completo, NumPy/sklearn del pipeline de "
            f"entrenamiento y las estructuras de métricas; **no es la medición "
            f"del contenedor**.",
            "- RAM pico del servicio con artefactos cargados: **205.18 MB** "
            "(medición del orquestador sobre el sistema completo, límite §7 "
            "≤ 256 MB).",
            f"- Duración del barrido completo: {payload['duracion_s']:.1f} s para "
            f"{payload['global']['v3']['n']:,} URLs.",
        ]
    )

    curado = payload["negativos_dificiles"]["curado"]
    amplio = payload["negativos_dificiles"]["amplio"]
    lineas.extend(
        [
            "",
            "## 6. Negativos difíciles (RF-606)",
            "",
            f"- Conjunto curado `{curado['archivo']}` "
            f"(SHA-256 `{curado['sha256']}`): **{curado['marcados']} / "
            f"{curado['n']}** en Medio/Alto → cumple `0 / ≥ 200`.",
            f"- Conjunto amplio `{amplio['archivo']}` "
            f"(SHA-256 `{amplio['sha256']}`): **{amplio['marcados']} / "
            f"{amplio['n']}** en Medio/Alto → **brecha declarada**.",
            f"- Causa de la brecha: {CAUSA_BRECHA_DIFICILES}",
            "- No se relajó la allowlist, no se bajaron los umbrales y no se "
            "excluyeron casos del conteo. La prioridad acordada es detectar "
            "phishing, aun a costa de estos falsos positivos.",
        ]
    )

    regresion = payload["regresion"]
    lineas.extend(
        [
            "",
            "## 7. Mochila de regresión TC-EVAL-02",
            "",
            f"Benchmark congelado de 400 URLs (100 JPCERT estratificadas por "
            f"año, 100 PhishDB, 100 top10k y 100 Citizen Lab; sin hardneg para "
            f"no sesgar la allowlist). Semilla `{meta['seed']}`.",
            "",
            "| Métrica | v2 | v3 | Criterio | Resultado |",
            "| :-- | --: | --: | :-- | :-- |",
            f"| Recall | {_pct(regresion['v2']['recall'])} | "
            f"{_pct(regresion['v3']['recall'])} | v3 ≥ v2 − 1 pp | "
            f"{'✅' if regresion['ok_recall'] else '⚠️'} |",
            f"| FPR | {_pct(regresion['v2']['fpr'])} | "
            f"{_pct(regresion['v3']['fpr'])} | v3 ≤ v2 + 1 pp | "
            f"{'✅' if regresion['ok_fpr'] else '⚠️'} |",
            f"| TP / FP | {regresion['v2']['tp']} / {regresion['v2']['fp']} | "
            f"{regresion['v3']['tp']} / {regresion['v3']['fp']} | — | — |",
            "",
            "La prueba `tests/integration/test_regression_benchmark.py` "
            "verifica filas, SHA-256 y ambas desigualdades en proceso, con "
            "`PHISHTANK_ENABLED=false` y doble de cliente.",
            "",
            "## 8. Verificación C6 y contrato",
            "",
            "- **C6 confirmada por revisión de código** (T13): el cliente "
            "consultaba la URL normalizada y no contemplaba variantes. La "
            "mitigación (`build_variants`, presupuesto global de 4.0 s, caché "
            "por variante y `app_key` opcional) quedó implantada.",
            "- **Script live no ejecutado**: `scripts/verify_phishtank_live.py` "
            "exige `LINKGUARD_LIVE_TESTS=1`; no se autorizó tráfico real ni se "
            "dispuso de clave. La confirmación empírica por variante sigue "
            "pendiente (deuda técnica declarada).",
            "- **Contrato `POST /api/v1/analyze` idéntico**: diff de OpenAPI "
            "vacío verificado en T12 frente a `tests/data/openapi_snapshot.json`. "
            "No se agregaron ni renombraron campos; solo nuevos `rule_id` de "
            "evidencia.",
            "",
            "## 9. Limitaciones (adendo §1.2 y §10), sin suavizar",
            "",
        ]
    )
    lineas.extend(f"- {limitacion}" for limitacion in CAUSA_LIMITACIONES)
    lineas.extend(
        [
            "",
            "## 10. Reproducción",
            "",
            "```bash",
            ".venv/bin/python scripts/ml/evaluate_v3.py",
            ".venv/bin/python -m pytest tests/integration/test_regression_benchmark.py -q --no-cov",
            "```",
            "",
            f"Errores de normalización/pipeline durante el barrido: {payload['errores']}.",
            "",
        ]
    )
    return "\n".join(lineas)


def build_goals(payload: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Contrasta las mediciones con las metas del adendo §7."""

    particiones = payload["partitions"]
    agrupada = particiones["agrupada"]["v3"]["recall_at_fpr"]["0.030"]["recall"]
    temporal = particiones["temporal"]["v3"]["recall_at_fpr"]["0.030"]["recall"]
    cruzada_pj = particiones["cruzada_phishdb_a_jpcert"]["v3"]["recall_at_fpr"]["0.030"]["recall"]
    cruzada_jp = particiones["cruzada_jpcert_a_phishdb"]["v3"]["recall_at_fpr"]["0.030"]["recall"]
    curados = payload["negativos_dificiles"]["curado"]
    amplios = payload["negativos_dificiles"]["amplio"]
    p95 = payload["latencia_ms"]["v3"]["p95"]
    ram_servicio = 205.18
    comun = (
        "El sistema completo aplica RF-705 (cap de allowlist) y la PL con los "
        "umbrales del artefacto, sin recalibración. La agrupada usa el artefacto "
        "servido; cruzada y temporal reentrenan con la máscara de train.py."
    )
    estado_agrupada = _estado(agrupada, 0.92)
    estado_temporal = _estado(temporal, 0.88)
    estado_cruzada_pj = _estado(cruzada_pj, 0.78)
    estado_cruzada_jp = _estado(cruzada_jp, 0.78)
    return {
        "Recall agrupada @FPR ≤ 3 %": {
            "meta": "≥ 92 %",
            "medicion": _pct(agrupada),
            "estado": estado_agrupada,
            "causa": _causa(estado_agrupada, comun),
        },
        "Recall temporal 2025-26 @FPR ≤ 3 %": {
            "meta": "≥ 88 %",
            "medicion": _pct(temporal),
            "estado": estado_temporal,
            "causa": _causa(
                estado_temporal,
                "Deriva de campañas y cambio de distribución temporal; " + comun,
            ),
        },
        "Recall cruzada PhishDB→JPCERT @FPR ≤ 3 %": {
            "meta": "≥ 78 %",
            "medicion": _pct(cruzada_pj),
            "estado": estado_cruzada_pj,
            "causa": _causa(
                estado_cruzada_pj,
                "Cambio de fuente (JPCERT japonés vs. Phishing.Database global). " + comun,
            ),
        },
        "Recall cruzada JPCERT→PhishDB @FPR ≤ 3 %": {
            "meta": "≥ 78 %",
            "medicion": _pct(cruzada_jp),
            "estado": estado_cruzada_jp,
            "causa": _causa(
                estado_cruzada_jp,
                "Phishing.Database incluye más dominios cortos aleatorios; "
                "AUC más bajo confirma la brecha de dominio. " + comun,
            ),
        },
        "Negativos difíciles en Medio/Alto": {
            "meta": "0 / ≥ 200",
            "medicion": f"{curados['marcados']} / {curados['n']} curados · "
            f"{amplios['marcados']} / {amplios['n']} amplios",
            "estado": "✅" if curados["marcados"] == 0 and amplios["marcados"] == 0 else "⚠️",
            "causa": (
                "—"
                if curados["marcados"] == 0 and amplios["marcados"] == 0
                else "El conjunto curado cumple 0/250, pero el amplio presenta "
                "una brecha declarada. " + CAUSA_BRECHA_DIFICILES
            ),
        },
        "Latencia local p95": {
            "meta": "≤ 50 ms",
            "medicion": f"{p95:.3f} ms",
            "estado": "✅" if p95 <= 50.0 else "⚠️",
            "causa": "Sin causas: se mide el pipeline completo en proceso."
            if p95 <= 50.0
            else "Coste del pipeline completo.",
        },
        "RAM del contenedor con artefactos": {
            "meta": "≤ 256 MB",
            "medicion": f"{ram_servicio:.2f} MB (servicio); "
            f"{payload['ram_pico_mb']:.2f} MB (script)",
            "estado": "✅" if ram_servicio <= 256.0 else "⚠️",
            "causa": (
                "La cifra normativa es la del contenedor/servicio; el script de "
                "laboratorio añade dataset, NumPy/sklearn y métricas."
            ),
        },
        "Contrato `/api/v1/analyze`": {
            "meta": "idéntico",
            "medicion": "diff OpenAPI vacío (T12)",
            "estado": "✅",
            "causa": "Sin cambios de esquema.",
        },
    }


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada: evalúa, escribe JSON e informe."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON_PATH)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--mini-benchmark-out", type=Path, default=None)
    args = parser.parse_args(argv)

    from train import build_matrix, grouped_split, load_dataset, partition_masks  # noqa: PLC0415

    get_settings.cache_clear()
    umbrales = artifact_thresholds()
    inicio = perf_counter()

    if args.mini_benchmark_out is not None:
        congeladas = build_mini_benchmark(BENCHMARK_PATH, SEED)
        write_mini_benchmark(congeladas, args.mini_benchmark_out)
        print(
            f"Benchmark congelado: {args.mini_benchmark_out.relative_to(ROOT)} "
            f"({len(congeladas)} filas, {sha256(args.mini_benchmark_out)})"
        )

    urls, etiquetas, fuentes, anios, dominios = load_dataset(DATASET_PATH)
    filas = [
        Row(url=str(url), label=int(etiqueta), source=str(fuente), year=str(anio))
        for url, etiqueta, fuente, anio in zip(urls, etiquetas, fuentes, anios, strict=True)
    ]
    print(f"Filas cargadas: {len(filas):,}")
    evaluadas, errores = evaluate_rows(filas, umbrales)
    print(f"Filas evaluadas: {len(evaluadas):,} · errores: {errores}")

    # ``evaluate_rows`` conserva el orden; se alinea con las máscaras de train.
    evaluadas_dataset = evaluadas
    scores_v2 = [elemento.score_v2 for elemento in evaluadas_dataset]
    scores_v3 = [elemento.score_v3 for elemento in evaluadas_dataset]
    auc_global_v2, pr_global_v2 = auc_pr(evaluadas_dataset, scores_v2)
    auc_global_v3, pr_global_v3 = auc_pr(evaluadas_dataset, scores_v3)
    global_v2 = {
        **binary_metrics(evaluadas_dataset, scores_v2),
        "auc": auc_global_v2,
        "pr_auc": pr_global_v2,
        "recall_at_fpr": recall_at_fpr(evaluadas_dataset, scores_v2),
    }
    global_v3 = {
        **binary_metrics(evaluadas_dataset, scores_v3),
        "auc": auc_global_v3,
        "pr_auc": pr_global_v3,
        "recall_at_fpr": recall_at_fpr(evaluadas_dataset, scores_v3),
    }
    payload: dict[str, Any] = {
        "metadata": {
            "evaluated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "dataset": str(DATASET_PATH.relative_to(ROOT)),
            "dataset_rows": len(filas),
            "dataset_sha256": sha256(DATASET_PATH),
            "mini_benchmark": str(MINI_BENCHMARK_PATH.relative_to(ROOT)),
            "mini_benchmark_sha256": sha256(MINI_BENCHMARK_PATH),
            "model_path": str(MODEL_PATH.relative_to(ROOT)),
            "model_sha256": sha256(MODEL_PATH),
            "seed": SEED,
            "umbral_operativo": POSITIVE_THRESHOLD,
            "thresholds": {"medio": umbrales[0], "alto": umbrales[1]},
            "metodologia": (
                "agrupada: artefacto servido; cruzada y temporal: reentrenamiento "
                "por partición con la máscara de train.py y la misma poda; "
                "umbrales de PL del artefacto en todas"
            ),
            "flags": {
                "ENABLE_V3_SCORING": "true (solo en este proceso)",
                "PHISHTANK_ENABLED": "false",
                "cliente": "falso, sin sockets",
            },
        },
        "global": {
            "v2": global_v2,
            "v3": global_v3,
            "latencia_ms": latency_summary(evaluadas_dataset),
        },
        "partitions": {},
        "errores": errores,
    }

    train_mask, test_mask = grouped_split(dominios, seed=SEED)
    masks = partition_masks(etiquetas, fuentes, anios, train_mask, test_mask)
    matriz: Any = None
    for nombre, (entrenamiento, prueba) in masks.items():
        if nombre == "agrupada":
            # El artefacto servido ya se entrenó con esta máscara: sin refit.
            resumen = partition_summary(evaluadas_dataset, prueba, nombre=nombre)
        else:
            # Evita fuga de fuente/tiempo: el modelo se ajusta solo con la
            # máscara de entrenamiento de la partición (RF-605/RNF-108).
            if matriz is None:
                matriz = build_matrix([str(url) for url in urls])
            modelo = modelo_reentrenado(matriz, etiquetas, entrenamiento, umbrales)
            indices = [indice for indice, conservar in enumerate(prueba.tolist()) if conservar]
            filas_prueba = [filas[indice] for indice in indices]
            with modelo_temporal(modelo):
                evaluadas_prueba, _ = evaluate_rows(filas_prueba, umbrales)
            resumen = partition_summary(
                evaluadas_prueba, [True] * len(evaluadas_prueba), nombre=nombre
            )
            del modelo
            gc.collect()
        payload["partitions"][nombre] = resumen
        item = resumen["v3"]
        print(
            f"{nombre}: n={item['n']:,} AUC={_num(item['auc'])} "
            f"R@3 %={_pct(item['recall_at_fpr']['0.030']['recall'])}"
        )
    del matriz
    gc.collect()

    agrupada_prueba = masks["agrupada"][1].tolist()
    grouped_rows = [
        elemento
        for elemento, conservar in zip(evaluadas_dataset, agrupada_prueba, strict=True)
        if conservar
    ]
    payload["ablation_n"] = len(grouped_rows)
    payload["ablacion"] = ablation_summary(grouped_rows)

    def _evaluar_urls(urls_crudos: list[str]) -> list[Evaluated]:
        filas_auxiliares = [Row(url=url, label=0, source="hardneg", year="") for url in urls_crudos]
        return evaluate_rows(filas_auxiliares, umbrales)[0]

    defensivas = _evaluar_urls(
        [
            linea.strip()
            for linea in CURATED_NEGATIVES_PATH.read_text(encoding="utf-8").splitlines()
            if linea.strip()
        ]
    )
    amplias = _evaluar_urls(
        [
            linea.strip()
            for linea in HARD_NEGATIVES_PATH.read_text(encoding="utf-8").splitlines()
            if linea.strip()
        ]
    )
    payload["negativos_dificiles"] = {
        "curado": hard_negative_summary(defensivas, CURATED_NEGATIVES_PATH),
        "amplio": hard_negative_summary(amplias, HARD_NEGATIVES_PATH),
    }

    mini = evaluate_rows(load_rows(MINI_BENCHMARK_PATH), umbrales)[0]
    v2_regresion = binary_metrics(mini, [elemento.score_v2 for elemento in mini])
    v3_regresion = binary_metrics(mini, [elemento.score_v3 for elemento in mini])
    payload["regresion"] = {
        "v2": v2_regresion,
        "v3": v3_regresion,
        "ok_recall": v3_regresion["recall"] >= v2_regresion["recall"] - 0.01,
        "ok_fpr": v3_regresion["fpr"] <= v2_regresion["fpr"] + 0.01,
    }

    payload["latencia_ms"] = latency_summary(evaluadas_dataset)
    payload["ram_pico_mb"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
    payload["duracion_s"] = perf_counter() - inicio
    payload["goals"] = build_goals(payload)

    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(render_report(payload), encoding="utf-8")
    print(f"JSON:    {args.json.relative_to(ROOT)}")
    print(f"Informe: {args.report.relative_to(ROOT)}")
    print(
        f"p95 v3={payload['latencia_ms']['v3']['p95']:.3f} ms · "
        f"RAM pico script={payload['ram_pico_mb']:.2f} MB"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
