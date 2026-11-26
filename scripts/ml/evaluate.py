"""Evalúa el motor léxico v2 en proceso sobre el benchmark (H5-T02).

El script ejecuta ``normalize -> run_rules -> score_results`` sin HTTP ni
PhishTank, reproduce la matriz de confusión del laboratorio (positivo =
Medio+Alto), calcula Recall@FPR y reporta las particiones agrupada por
dominio, cruzada entre fuentes y temporal. Genera un informe Markdown y un
JSON con los resultados.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from urllib.parse import urlsplit

from publicsuffix2 import get_sld

ROOT: Path = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PROCESSED_DIR: Path = ROOT / "data" / "processed"
DEFAULT_INPUT: Path = PROCESSED_DIR / "benchmark.tsv"
DEFAULT_REPORT: Path = ROOT / "docs" / "reports" / "accuracy-baseline-v2.md"
DEFAULT_JSON: Path = PROCESSED_DIR / "baseline_v2.json"

#: Frontera inferior de Medio (positivo operativo del contrato, RF-302).
MEDIUM_THRESHOLD: int = 31
FPR_TARGETS: tuple[float, ...] = (0.003, 0.01, 0.03, 0.05)

#: Referencias del laboratorio (accuracy-lab/RESULTS.md).
LAB_RECALL: float = 0.019
LAB_F1: float = 0.037
LAB_JPCERT_BAJO: float = 0.984


@dataclass(frozen=True, slots=True)
class Row:
    """Fila etiquetada del benchmark."""

    url: str
    label: int
    source: str
    year: str


@dataclass(frozen=True, slots=True)
class Result:
    """Resultado de evaluar una fila con el motor v2."""

    row: Row
    score: int
    level: str
    rules: tuple[str, ...]
    latency_ms: float


def _sha256(path: Path) -> str:
    """Calcula el SHA-256 de un archivo por bloques."""
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _host(url: str) -> str:
    """Extrae el host en minúsculas de una URL o de un dominio suelto."""
    candidate = url if "://" in url else f"http://{url}"
    return (urlsplit(candidate).hostname or "").lower()


def _registrable_domain(url: str) -> str:
    """Devuelve el dominio registrable (eTLD+1) de una URL."""
    host = _host(url)
    return get_sld(host) or host


def load_rows(path: Path) -> list[Row]:
    """Carga el TSV etiquetado (``url``, ``label``, ``source``, ``year``)."""
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        rows: list[Row] = []
        for record in reader:
            url = (record.get("url") or "").strip()
            if not url:
                continue
            rows.append(
                Row(
                    url=url,
                    label=int(record.get("label") or 0),
                    source=(record.get("source") or "").strip(),
                    year=(record.get("year") or "").strip(),
                )
            )
        return rows


def evaluate_rows(rows: list[Row]) -> tuple[list[Result], int]:
    """Ejecuta el motor v2 en proceso y devuelve resultados y errores."""
    from app.engine.pipeline import run_rules
    from app.normalization import normalize
    from app.scoring.scorer import score_results

    results: list[Result] = []
    errors = 0
    for row in rows:
        started = perf_counter()
        try:
            parsed = normalize(row.url)
            rules = run_rules(parsed)
            scoring = score_results(rules)
        except Exception:  # el laboratorio cuenta el error y continúa
            errors += 1
            results.append(
                Result(
                    row=row,
                    score=-1,
                    level="error",
                    rules=(),
                    latency_ms=(perf_counter() - started) * 1000.0,
                )
            )
            continue
        results.append(
            Result(
                row=row,
                score=scoring.score,
                level=scoring.risk_level.value,
                rules=tuple(rule.rule_id for rule in rules if rule.activated),
                latency_ms=(perf_counter() - started) * 1000.0,
            )
        )
    return results, errors


def _confusion(
    results: list[Result], threshold: int = MEDIUM_THRESHOLD
) -> tuple[int, int, int, int]:
    """Cuenta TP, FN, FP y TN usando ``score >= threshold`` como positivo."""
    tp = fn = fp = tn = 0
    for result in results:
        if result.score < 0:
            continue
        predicted = result.score >= threshold
        if result.row.label == 1:
            if predicted:
                tp += 1
            else:
                fn += 1
        elif predicted:
            fp += 1
        else:
            tn += 1
    return tp, fn, fp, tn


def _metrics(tp: int, fn: int, fp: int, tn: int) -> dict[str, float]:
    """Calcula precisión, recall, F1 y exactitud."""
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    total = tp + fn + fp + tn
    accuracy = (tp + tn) / total if total else 0.0
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "accuracy": accuracy,
        "fpr": fp / (fp + tn) if fp + tn else 0.0,
    }


def _recall_at_fpr(
    results: list[Result],
    targets: tuple[float, ...] = FPR_TARGETS,
) -> list[tuple[float, float, int]]:
    """Calcula el máximo recall alcanzable con FPR <= objetivo."""
    scores = sorted({result.score for result in results if result.score >= 0}, reverse=True)
    thresholds = [101, *scores]
    output: list[tuple[float, float, int]] = []
    for target in targets:
        best_recall = 0.0
        best_threshold = 101
        for threshold in thresholds:
            tp, fn, fp, tn = _confusion(results, threshold)
            fpr = fp / (fp + tn) if fp + tn else 0.0
            recall = tp / (tp + fn) if tp + fn else 0.0
            if fpr <= target and recall >= best_recall:
                best_recall = recall
                best_threshold = threshold
        output.append((target, best_recall, best_threshold))
    return output


def _grouped_partition(
    results: list[Result],
    *,
    seed: int = 7,
    test_fraction: float = 0.3,
) -> list[Result]:
    """Separa el 30 % de los dominios registrables para evaluar en reserva."""
    groups: dict[str, list[Result]] = defaultdict(list)
    for result in results:
        groups[_registrable_domain(result.row.url)].append(result)
    domains = sorted(groups)
    random.Random(seed).shuffle(domains)
    split = int(len(domains) * (1.0 - test_fraction))
    test_domains = set(domains[split:])
    return [result for result in results if _registrable_domain(result.row.url) in test_domains]


def _per_source(results: list[Result]) -> dict[str, dict[str, object]]:
    """Agrupa las métricas por fuente."""
    grouped: dict[str, list[Result]] = defaultdict(list)
    for result in results:
        grouped[result.row.source].append(result)
    summary: dict[str, dict[str, object]] = {}
    for source, items in sorted(grouped.items()):
        tp, fn, fp, tn = _confusion(items)
        levels = Counter(result.level for result in items)
        summary[source] = {
            "n": len(items),
            "Bajo": levels["Bajo"],
            "Medio": levels["Medio"],
            "Alto": levels["Alto"],
            **_metrics(tp, fn, fp, tn),
        }
    return summary


def _per_year(results: list[Result]) -> dict[str, dict[str, object]]:
    """Desglosa JPCERT por año."""
    grouped: dict[str, list[Result]] = defaultdict(list)
    for result in results:
        if result.row.source == "jpcert" and result.row.year.isdigit():
            grouped[result.row.year].append(result)
    summary: dict[str, dict[str, object]] = {}
    for year, items in sorted(grouped.items()):
        levels = Counter(result.level for result in items)
        positives = sum(1 for result in items if result.row.label == 1)
        flagged = levels["Medio"] + levels["Alto"]
        summary[year] = {
            "n": len(items),
            "positivos": positives,
            "Bajo": levels["Bajo"],
            "Medio": levels["Medio"],
            "Alto": levels["Alto"],
            "recall": flagged / positives if positives else 0.0,
        }
    return summary


def _temporal(results: list[Result]) -> dict[str, dict[str, object]]:
    """Compara JPCERT <= 2023 contra 2025-2026."""
    summary: dict[str, dict[str, object]] = {}
    for name, predicate in (
        ("old", lambda year: year <= 2023),
        ("new", lambda year: year >= 2025),
    ):
        items = [
            result
            for result in results
            if result.row.source == "jpcert"
            and result.row.year.isdigit()
            and predicate(int(result.row.year))
        ]
        levels = Counter(result.level for result in items)
        positives = sum(1 for result in items if result.row.label == 1)
        summary[name] = {
            "n": len(items),
            "positivos": positives,
            "recall": (levels["Medio"] + levels["Alto"]) / positives if positives else 0.0,
        }
    return summary


def _percentile(values: list[float], fraction: float) -> float:
    """Percentil simple por interpolación discreta."""
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round((len(ordered) - 1) * fraction)))
    return ordered[index]


def _pct(value: float) -> str:
    """Formatea una fracción como porcentaje con un decimal."""
    return f"{value * 100:.1f} %"


def _delta_pct(value: float, reference: float) -> str:
    """Diferencia en puntos porcentuales."""
    return f"{(value - reference) * 100:+.1f} pp"


def _top_rules(results: list[Result], limit: int = 15) -> list[tuple[str, int, float]]:
    """Cuenta las reglas activadas con más frecuencia."""
    counter: Counter[str] = Counter()
    for result in results:
        counter.update(result.rules)
    total = max(1, sum(1 for result in results if result.score >= 0))
    return [(rule, count, count / total) for rule, count in counter.most_common(limit)]


def _comparison(metrics: dict[str, float], jpcert_bajo: float) -> str:
    """Redacta la comparación con la línea base del laboratorio."""
    recall_gap = abs(metrics["recall"] - LAB_RECALL)
    f1_gap = abs(metrics["f1"] - LAB_F1)
    bajo_gap = abs(jpcert_bajo - LAB_JPCERT_BAJO)
    if recall_gap <= 0.01 and f1_gap <= 0.01 and bajo_gap <= 0.01:
        return (
            "La medición **reproduce la línea base dentro de ±1 punto**: recall, "
            "F1 y proporción de Bajo en JPCERT coinciden con `RESULTS.md`."
        )
    reasons = [
        "El conjunto de negativos de este benchmark no es idéntico al del "
        "laboratorio (3 048): las bandas de ranking y el cap de 3 URLs por "
        "dominio cambian la composición.",
        "La muestra positiva se re-estratificó por año con cap de 3 URLs por dominio registrable.",
        "Los datos de JPCERT y Phishing.Database se descargaron el "
        f"{datetime.now(UTC).date().isoformat()}; el repositorio pudo cambiar "
        "respecto de la medición del 24-nov-2026.",
        "El motor v2 y la PSL (`publicsuffix2` 2019) son deterministas: la "
        "desviación proviene del muestreo y de la actualización de las fuentes, "
        "no de aleatoriedad del motor.",
    ]
    return "La medición **difiere en más de ±1 punto** de la referencia. Causas:\n\n" + "\n".join(
        f"- {reason}" for reason in reasons
    )


def _build_report(
    *,
    input_path: Path,
    rows: list[Row],
    results: list[Result],
    errors: int,
    metrics: dict[str, float],
    tp: int,
    fn: int,
    fp: int,
    tn: int,
    sources: dict[str, dict[str, object]],
    recall_at_fpr: list[tuple[float, float, int]],
    grouped: dict[str, object],
    temporal: dict[str, dict[str, object]],
    per_year: dict[str, dict[str, object]],
    latency: dict[str, float],
    top_rules: list[tuple[str, int, float]],
) -> str:
    """Construye el informe Markdown de la línea base."""
    jpcert_bajo = float(sources.get("jpcert", {}).get("Bajo", 0)) / max(
        1, int(sources.get("jpcert", {}).get("n", 0))
    )
    lines: list[str] = [
        "# Línea base del motor v2 — H5-T02",
        "",
        f"**Fecha:** {datetime.now(UTC).isoformat()}",
        f"**Dataset:** `{input_path.relative_to(ROOT)}` (SHA-256 `{_sha256(input_path)}`)",
        f"**Filas:** {len(rows)} · **Errores de normalización:** {errors}",
        "**Motor:** v2 (`normalize -> run_rules -> score_results`), en proceso, "
        "sin PhishTank ni HTTP.",
        "",
        "## 1. Resumen global",
        "",
        "| Métrica | Valor |",
        "| :-- | --: |",
        f"| TP (Medio+Alto en positivos) | {tp} |",
        f"| FN (Bajo en positivos) | {fn} |",
        f"| FP (Medio+Alto en negativos) | {fp} |",
        f"| TN (Bajo en negativos) | {tn} |",
        f"| Precisión | {metrics['precision']:.3f} |",
        f"| Recall | {metrics['recall']:.3f} ({_pct(metrics['recall'])}) |",
        f"| F1 | {metrics['f1']:.3f} |",
        f"| Exactitud | {metrics['accuracy']:.3f} |",
        f"| FPR | {metrics['fpr']:.3f} ({_pct(metrics['fpr'])}) |",
        "",
        "### Comparación con el laboratorio",
        "",
        "| Métrica | `RESULTS.md` | Medición | Δ |",
        "| :-- | --: | --: | --: |",
        f"| Recall | {LAB_RECALL:.3f} | {metrics['recall']:.3f} | "
        f"{_delta_pct(metrics['recall'], LAB_RECALL)} |",
        f"| F1 | {LAB_F1:.3f} | {metrics['f1']:.3f} | {metrics['f1'] - LAB_F1:+.3f} |",
        f"| JPCERT Bajo | {_pct(LAB_JPCERT_BAJO)} | {_pct(jpcert_bajo)} | "
        f"{_delta_pct(jpcert_bajo, LAB_JPCERT_BAJO)} |",
        "",
        _comparison(metrics, jpcert_bajo),
        "",
        "## 2. Matriz de confusión por fuente",
        "",
        "| Fuente | n | Bajo | Medio | Alto | % Bajo | % Medio+Alto |",
        "| :-- | --: | --: | --: | --: | --: | --: |",
    ]
    for source, item in sources.items():
        n = max(1, int(item["n"]))
        flagged = int(item["Medio"]) + int(item["Alto"])
        lines.append(
            f"| {source} | {item['n']} | {item['Bajo']} | {item['Medio']} | "
            f"{item['Alto']} | {_pct(int(item['Bajo']) / n)} | "
            f"{_pct(flagged / n)} |"
        )

    lines.extend(
        [
            "",
            "## 3. Recall@FPR (barrido del score)",
            "",
            "El motor v2 no expone probabilidades; se barre el umbral de score "
            "para trazar la curva y se reporta el máximo recall con FPR <= objetivo.",
            "",
            "| FPR objetivo | Recall máximo | Umbral de score |",
            "| --: | --: | --: |",
        ]
    )
    for target, recall, threshold in recall_at_fpr:
        lines.append(f"| {_pct(target)} | {_pct(recall)} | {threshold} |")

    lines.extend(
        [
            "",
            "## 4. Particiones",
            "",
            "### 4.1 Agrupada por dominio registrable (70/30)",
            "",
            "| Métrica | Valor |",
            "| :-- | --: |",
            f"| n (30 % de dominios en reserva) | {grouped['n']} |",
            f"| Positivos | {grouped['positivos']} |",
            f"| Negativos | {grouped['negativos']} |",
            f"| Recall | {grouped['recall']:.3f} ({_pct(float(grouped['recall']))}) |",
            f"| FPR | {grouped['fpr']:.3f} ({_pct(float(grouped['fpr']))}) |",
            f"| F1 | {grouped['f1']:.3f} |",
            "",
            "### 4.2 Cruzada entre fuentes",
            "",
            "| Fuente positiva | n | Recall | % Bajo |",
            "| :-- | --: | --: | --: |",
        ]
    )
    for source in ("jpcert", "phishdb"):
        item = sources.get(source)
        if item is None:
            continue
        n = max(1, int(item["n"]))
        lines.append(
            f"| {source} | {item['n']} | {_pct(float(item['recall']))} | "
            f"{_pct(int(item['Bajo']) / n)} |"
        )

    lines.extend(
        [
            "",
            "### 4.3 Temporal (JPCERT)",
            "",
            "| Partición | Positivos | Recall |",
            "| :-- | --: | --: |",
            f"| JPCERT <= 2023 | {temporal['old']['positivos']} | "
            f"{_pct(float(temporal['old']['recall']))} |",
            f"| JPCERT 2025-2026 | {temporal['new']['positivos']} | "
            f"{_pct(float(temporal['new']['recall']))} |",
            "",
            "## 5. Desglose por año (JPCERT)",
            "",
            "| Año | Positivos | Bajo | Medio | Alto | Recall |",
            "| :-- | --: | --: | --: | --: | --: |",
        ]
    )
    for year, item in per_year.items():
        lines.append(
            f"| {year} | {item['positivos']} | {item['Bajo']} | {item['Medio']} | "
            f"{item['Alto']} | {_pct(float(item['recall']))} |"
        )

    lines.extend(
        [
            "",
            "## 6. Latencia local",
            "",
            "| Métrica | ms/URL |",
            "| :-- | --: |",
            f"| p50 | {latency['p50']:.3f} |",
            f"| p95 | {latency['p95']:.3f} |",
            f"| Media | {latency['mean']:.3f} |",
            "",
            "## 7. Reglas más activadas",
            "",
            "| Regla | Activaciones | % de URLs |",
            "| :-- | --: | --: |",
        ]
    )
    for rule, count, fraction in top_rules:
        lines.append(f"| {rule} | {count} | {_pct(fraction)} |")

    lines.extend(
        [
            "",
            "## 8. Limitaciones",
            "",
            "- Negativos tomados de rankings populares: el FPR sobre sitios "
            "legítimos pequeños (fuera del top-1M) no se mide.",
            "- Positivos de JPCERT y Phishing.Database ya dados de baja o "
            "agregados: no equivalen a phishing recién creado.",
            "- La edad de dominio, DNS y certificados no se miden en este "
            "laboratorio (candidatos a `RF-901`, condicional).",
            "- El motor v2 tiene un techo estructural de recall: suma de señales "
            "débiles y umbral Alto de 70 puntos. Este informe es la línea base "
            "que el modelo lineal de `H5-T09` debe superar.",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada de la evaluación de la línea base v2."""
    parser = argparse.ArgumentParser(description="Evalúa la línea base del motor v2.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="TSV de entrada.")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT, help="Informe Markdown.")
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON, help="Salida JSON.")
    parser.add_argument("--seed", type=int, default=7, help="Semilla de la partición agrupada.")
    args = parser.parse_args(argv)

    rows = load_rows(args.input)
    results, errors = evaluate_rows(rows)
    tp, fn, fp, tn = _confusion(results)
    metrics = _metrics(tp, fn, fp, tn)
    sources = _per_source(results)
    recall_at_fpr = _recall_at_fpr(results)
    per_year = _per_year(results)
    temporal = _temporal(results)

    grouped_results = _grouped_partition(results, seed=args.seed)
    grouped_tp, grouped_fn, grouped_fp, grouped_tn = _confusion(grouped_results)
    grouped_metrics = _metrics(grouped_tp, grouped_fn, grouped_fp, grouped_tn)
    grouped = {
        "n": len(grouped_results),
        "positivos": sum(1 for result in grouped_results if result.row.label == 1),
        "negativos": sum(1 for result in grouped_results if result.row.label == 0),
        **grouped_metrics,
    }

    latencies = [result.latency_ms for result in results if result.score >= 0]
    latency = {
        "p50": _percentile(latencies, 0.50),
        "p95": _percentile(latencies, 0.95),
        "mean": sum(latencies) / len(latencies) if latencies else 0.0,
    }
    top_rules = _top_rules(results)

    report = _build_report(
        input_path=args.input,
        rows=rows,
        results=results,
        errors=errors,
        metrics=metrics,
        tp=tp,
        fn=fn,
        fp=fp,
        tn=tn,
        sources=sources,
        recall_at_fpr=recall_at_fpr,
        grouped=grouped,
        temporal=temporal,
        per_year=per_year,
        latency=latency,
        top_rules=top_rules,
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(report + "\n", encoding="utf-8")

    payload = {
        "evaluated_at": datetime.now(UTC).isoformat(),
        "input": str(args.input.relative_to(ROOT)),
        "input_sha256": _sha256(args.input),
        "rows": len(rows),
        "errors": errors,
        "summary": {"tp": tp, "fn": fn, "fp": fp, "tn": tn, **metrics},
        "sources": sources,
        "recall_at_fpr": [
            {"target": target, "recall": recall, "threshold": threshold}
            for target, recall, threshold in recall_at_fpr
        ],
        "grouped": grouped,
        "temporal": temporal,
        "per_year": per_year,
        "latency_ms": latency,
        "top_rules": [
            {"rule": rule, "activations": count, "fraction": fraction}
            for rule, count, fraction in top_rules
        ],
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"Informe: {args.report.relative_to(ROOT)}")
    print(f"JSON:    {args.json.relative_to(ROOT)}")
    print(
        f"Recall={metrics['recall']:.3f} F1={metrics['f1']:.3f} "
        f"FPR={metrics['fpr']:.3f} errores={errors}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
