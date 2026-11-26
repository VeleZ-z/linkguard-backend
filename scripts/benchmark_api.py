"""Benchmark de humo contra la API de LinkGuard (H5-T03).

Modos:

* ``--local``: ejecuta la app ASGI en proceso (sin red y con el limitador
  desactivado). La reputación externa se desactiva con
  ``PHISHTANK_ENABLED=false``, que el analizador respeta sin necesidad de
  parchear funciones internas.
* ``--remote``: envía como máximo 300 URLs a la API desplegada respetando el
  límite configurado (25 peticiones por minuto por defecto). Antes de empezar
  consulta ``GET /health`` y reintenta ante HTTP 429 respetando
  ``Retry-After``.

El CSV de salida contiene únicamente ``url_hash`` (SHA-256), ``label``,
``source``, ``score``, ``nivel`` y ``phishtank_status``. Nunca se imprime ni
se persiste la URL en claro.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import logging
import os
import random
import sys
import time
from collections import Counter
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Final

import httpx

ROOT: Path = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PROCESSED_DIR: Path = ROOT / "data" / "processed"
DEFAULT_INPUT: Path = PROCESSED_DIR / "benchmark.tsv"
DEFAULT_BASE_URL: str = os.environ.get("LINKGUARD_API_URL", "http://localhost:8000")
FIELDNAMES: Final[tuple[str, ...]] = (
    "url_hash",
    "label",
    "source",
    "score",
    "nivel",
    "phishtank_status",
)

#: Máximo de URLs permitido en modo remoto.
REMOTE_MAX_URLS: Final[int] = 300
#: Peticiones por minuto por defecto en modo remoto.
DEFAULT_RATE: Final[float] = 25.0
#: Reintentos ante HTTP 429 antes de marcar la fila como error.
MAX_RETRIES: Final[int] = 3
#: Espera por defecto si el 429 no trae ``Retry-After`` válido, en segundos.
DEFAULT_RETRY_AFTER: Final[float] = 60.0
#: Niveles que cuentan como positivo operativo (Medio+Alto, RF-302).
FLAGGED_LEVELS: Final[frozenset[str]] = frozenset({"Medio", "Alto"})

#: Muestra del benchmark: ``(url, label, source)``.
Sample = tuple[str, int, str]

#: Indirección para que las pruebas no esperen de verdad entre peticiones.
_sleep: Callable[[float], None] = time.sleep


class DatasetFormatError(ValueError):
    """El dataset de entrada no tiene la columna obligatoria ``url``."""


def _url_hash(url: str) -> str:
    """Devuelve el SHA-256 de la URL; es lo único que se persiste."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def _parse_label(value: object) -> int:
    """Normaliza la etiqueta a 0/1; cualquier valor no numérico es negativo."""
    try:
        return 1 if int(str(value).strip()) > 0 else 0
    except (TypeError, ValueError):
        return 0


def _stratified(
    samples: list[Sample],
    max_urls: int,
    rng: random.Random,
) -> list[Sample]:
    """Selecciona mitad positivos y mitad negativos, con orden reproducible."""
    positives = [sample for sample in samples if sample[1] == 1]
    negatives = [sample for sample in samples if sample[1] == 0]
    rng.shuffle(positives)
    rng.shuffle(negatives)

    if max_urls == 0:
        per_class = min(len(positives), len(negatives))
    else:
        per_class = max_urls // 2
        if per_class == 0:
            return [rng.choice(samples)] if samples else []

    per_class = min(per_class, len(positives), len(negatives))
    selected = positives[:per_class] + negatives[:per_class]
    rng.shuffle(selected)
    return selected


def load_urls(
    path: Path,
    max_urls: int,
    seed: int,
    *,
    stratify: bool = False,
) -> list[Sample]:
    """Carga ``(url, label, source)`` desde un TSV etiquetado.

    Args:
        path: TSV con encabezado y, como mínimo, la columna ``url``.
        max_urls: Tope de muestras; ``0`` significa sin límite.
        seed: Semilla del muestreo reproducible.
        stratify: Si es ``True``, devuelve mitad positivos y mitad negativos.

    Raises:
        DatasetFormatError: Si el encabezado no contiene la columna ``url``.
        ValueError: Si ``max_urls`` es negativo.
    """
    if max_urls < 0:
        raise ValueError("max_urls no puede ser negativo")

    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        fieldnames = reader.fieldnames or []
        if "url" not in fieldnames:
            found = ", ".join(fieldnames) if fieldnames else "ninguna"
            raise DatasetFormatError(
                f"El dataset {path} debe incluir la columna 'url' (columnas encontradas: {found})"
            )

        samples: dict[str, Sample] = {}
        for record in reader:
            url = (record.get("url") or "").strip()
            if not url or url in samples:
                continue
            samples[url] = (
                url,
                _parse_label(record.get("label")),
                (record.get("source") or "").strip(),
            )

    ordered = list(samples.values())
    rng = random.Random(seed)
    if stratify:
        return _stratified(ordered, max_urls, rng)
    if max_urls and len(ordered) > max_urls:
        ordered = rng.sample(ordered, max_urls)
    return ordered


def _row_from_response(
    sample: Sample,
    status_code: int,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Construye una fila del CSV a partir de la respuesta HTTP."""
    url, label, source = sample
    base: dict[str, Any] = {
        "url_hash": _url_hash(url),
        "label": label,
        "source": source,
    }
    if status_code == 200:
        return {
            **base,
            "score": payload.get("score", ""),
            "nivel": payload.get("risk_level", ""),
            "phishtank_status": payload.get("phishtank_status", ""),
        }
    return {
        **base,
        "score": "",
        "nivel": "error",
        "phishtank_status": f"http_{status_code}",
    }


def _error_row(sample: Sample, status: str) -> dict[str, Any]:
    """Fila de error sin URL en claro (fallo de red u otro)."""
    url, label, source = sample
    return {
        "url_hash": _url_hash(url),
        "label": label,
        "source": source,
        "score": "",
        "nivel": "error",
        "phishtank_status": status,
    }


def run_local(samples: Sequence[Sample]) -> list[dict[str, Any]]:
    """Ejecuta el benchmark contra la app ASGI en proceso.

    La reputación externa se apaga con ``PHISHTANK_ENABLED=false`` (leída por
    ``Settings`` y respetada por el analizador) y el limitador se desactiva
    durante la ejecución. Ambos ajustes se restauran al terminar.
    """
    from app.core.config import get_settings
    from app.core.rate_limit import limiter
    from app.main import app

    logger = logging.getLogger("linkguard")
    previous_level = logger.level
    previous_limiter = limiter.enabled
    previous_env = os.environ.get("PHISHTANK_ENABLED")

    os.environ["PHISHTANK_ENABLED"] = "false"
    get_settings.cache_clear()
    limiter.enabled = False
    # El benchmark no necesita la telemetría por petición; se silencia para
    # que la salida del script sea legible. La app sigue registrando solo hashes.
    logger.setLevel(logging.WARNING)

    try:

        async def _execute() -> list[dict[str, Any]]:
            rows: list[dict[str, Any]] = []
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
                timeout=30.0,
            ) as client:
                for sample in samples:
                    response = await client.post(
                        "/api/v1/analyze",
                        json={"url": sample[0]},
                    )
                    try:
                        payload = response.json()
                    except ValueError:
                        payload = {}
                    rows.append(_row_from_response(sample, response.status_code, payload))
            return rows

        return asyncio.run(_execute())
    finally:
        if previous_env is None:
            os.environ.pop("PHISHTANK_ENABLED", None)
        else:
            os.environ["PHISHTANK_ENABLED"] = previous_env
        get_settings.cache_clear()
        limiter.enabled = previous_limiter
        logger.setLevel(previous_level)


def _warm_up(client: httpx.Client, base_url: str) -> None:
    """Consulta ``GET /health`` antes de medir; un fallo no aborta el benchmark."""
    try:
        client.get(f"{base_url}/health")
    except httpx.HTTPError:
        print(
            "Advertencia: /health no respondió; se continúa con el benchmark.",
            file=sys.stderr,
        )


def _retry_after(response: httpx.Response) -> float:
    """Lee ``Retry-After`` en segundos; si no es válido usa el valor por defecto."""
    raw = response.headers.get("Retry-After")
    if raw:
        try:
            return max(0.0, float(raw.strip()))
        except ValueError:
            pass
    return DEFAULT_RETRY_AFTER


def run_remote(
    samples: Sequence[Sample],
    base_url: str,
    rate: float,
) -> list[dict[str, Any]]:
    """Ejecuta el benchmark contra una API desplegada respetando el rate limit.

    Ante HTTP 429 espera ``Retry-After`` (o 60 s) y reintenta hasta
    ``MAX_RETRIES`` veces. Si se agotan, la fila queda como ``http_429``.
    """
    rows: list[dict[str, Any]] = []
    base = base_url.rstrip("/")
    endpoint = f"{base}/api/v1/analyze"
    delay = 60.0 / rate if rate > 0 else 0.0

    with httpx.Client(timeout=30.0) as client:
        _warm_up(client, base)

        for index, sample in enumerate(samples):
            if index and delay:
                _sleep(delay)

            response: httpx.Response | None = None
            for attempt in range(MAX_RETRIES + 1):
                try:
                    response = client.post(endpoint, json={"url": sample[0]})
                except httpx.HTTPError:
                    response = None
                    break

                if response.status_code != 429 or attempt == MAX_RETRIES:
                    break
                _sleep(_retry_after(response))

            if response is None:
                rows.append(_error_row(sample, "network_error"))
                continue

            payload: dict[str, Any] = {}
            if response.status_code == 200:
                try:
                    decoded = response.json()
                except ValueError:
                    decoded = {}
                if isinstance(decoded, dict):
                    payload = decoded
            rows.append(_row_from_response(sample, response.status_code, payload))

    return rows


def summarize(rows: Sequence[dict[str, Any]]) -> dict[str, float | int | None]:
    """Calcula recall (Medio+Alto sobre positivos) y FPR sobre negativos."""
    positives = [row for row in rows if _parse_label(row.get("label")) == 1]
    negatives = [row for row in rows if _parse_label(row.get("label")) == 0]

    def flagged(items: Sequence[dict[str, Any]]) -> int:
        return sum(1 for row in items if str(row.get("nivel")) in FLAGGED_LEVELS)

    tp = flagged(positives)
    fp = flagged(negatives)
    return {
        "positivos": len(positives),
        "negativos": len(negatives),
        "tp": tp,
        "fp": fp,
        "recall": tp / len(positives) if positives else None,
        "fpr": fp / len(negatives) if negatives else None,
    }


def _print_summary(summary: dict[str, float | int | None]) -> None:
    """Imprime recall y FPR sin exponer ninguna URL."""
    recall = summary["recall"]
    fpr = summary["fpr"]
    recall_text = f"{recall * 100:.1f} %" if isinstance(recall, float) else "n/d"
    fpr_text = f"{fpr * 100:.1f} %" if isinstance(fpr, float) else "n/d"
    print("Resumen (--summary):")
    print(f"  Positivos: {summary['positivos']} · Recall (Medio+Alto): {recall_text}")
    print(f"  Negativos: {summary['negativos']} · FPR (Medio+Alto): {fpr_text}")


def write_csv(rows: list[dict[str, Any]], output: Path) -> None:
    """Escribe el CSV de resultados sin URLs en claro."""
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def _display_path(path: Path) -> str:
    """Devuelve una ruta imprimible aunque quede fuera del repositorio."""
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(ROOT))
    except ValueError:
        return str(resolved)


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada del benchmark de humo."""
    parser = argparse.ArgumentParser(description="Benchmark de humo de la API LinkGuard.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--local", action="store_true", help="ASGI en proceso.")
    mode.add_argument("--remote", action="store_true", help="API desplegada.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="TSV de URLs.")
    parser.add_argument("--output", type=Path, default=None, help="CSV de salida.")
    parser.add_argument(
        "--max-urls",
        type=int,
        default=REMOTE_MAX_URLS,
        help="Máximo de URLs; 0 = sin límite en modo local.",
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="URL base de la API remota.")
    parser.add_argument(
        "--rate",
        type=float,
        default=DEFAULT_RATE,
        help="Peticiones por minuto en modo remoto (por defecto 25).",
    )
    parser.add_argument("--seed", type=int, default=7, help="Semilla del muestreo.")
    parser.add_argument(
        "--stratify",
        action="store_true",
        help="Selecciona mitad positivos y mitad negativos.",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Imprime recall (Medio+Alto) y FPR al finalizar.",
    )
    args = parser.parse_args(argv)

    if args.max_urls < 0:
        parser.error("--max-urls no puede ser negativo")
    if args.remote and not 1 <= args.max_urls <= REMOTE_MAX_URLS:
        parser.error(f"En modo remoto --max-urls debe estar entre 1 y {REMOTE_MAX_URLS}")

    try:
        samples = load_urls(
            args.input,
            args.max_urls,
            args.seed,
            stratify=args.stratify,
        )
    except DatasetFormatError as exc:
        parser.error(str(exc))

    if args.local:
        rows = run_local(samples)
        output = args.output or PROCESSED_DIR / "benchmark_api_local.csv"
    else:
        rows = run_remote(samples, args.base_url, args.rate)
        output = args.output or PROCESSED_DIR / "benchmark_api_remote.csv"

    write_csv(rows, output)
    levels = Counter(str(row["nivel"]) for row in rows)
    statuses = Counter(str(row["phishtank_status"]) for row in rows)
    print(f"Salida: {_display_path(output)}")
    print(f"URLs:   {len(rows)}")
    print(f"Niveles: {dict(levels)}")
    print(f"Estados: {dict(statuses)}")
    if args.summary:
        _print_summary(summarize(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
