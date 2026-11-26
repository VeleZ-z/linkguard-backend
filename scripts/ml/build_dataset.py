"""Construye los conjuntos de datos etiquetados del Hito 5 (H5-T02).

El script implementa dos perfiles:

* ``benchmark``: composición compatible con el laboratorio (2 400 JPCERT
  estratificados por año + 2 400 Phishing.Database + 3 048 negativos) para
  reproducir la línea base v2.
* ``train``: receta de entrenamiento con cap de 3 URLs por dominio registrable
  y negativos por bandas de ranking (1k/10k/100k/1M), con rutas legítimas
  reales en el 50 % de los casos.

Todas las muestras usan semillas fijas. La salida se escribe en
``data/processed/`` junto con un manifiesto que incluye conteos y SHA-256.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from publicsuffix2 import get_sld

ROOT: Path = Path(__file__).resolve().parents[2]
RAW_DIR: Path = ROOT / "data" / "raw"
PROCESSED_DIR: Path = ROOT / "data" / "processed"
HARD_NEGATIVES: Path = ROOT / "docs" / "specs" / "accuracy-lab" / "data" / "hard_negatives_seed.txt"

#: Bandas de ranking de Tranco: (inicio_exclusivo, fin_inclusivo, muestras).
BANDS: tuple[tuple[int, int, int], ...] = (
    (0, 1_000, 1_000),
    (1_000, 10_000, 6_000),
    (10_000, 100_000, 14_000),
    (100_000, 1_000_000, 15_000),
)

#: Tamaños del perfil de benchmark (compatibles con accuracy-lab/RESULTS.md).
BENCHMARK_JPCERT_PER_YEAR: int = 300
BENCHMARK_PHISHDB: int = 2_400
BENCHMARK_TOP10K: int = 1_500
BENCHMARK_CITIZENLAB: int = 1_500

#: Tamaños del perfil de entrenamiento.
TRAIN_JPCERT: int = 20_000
TRAIN_PHISHDB: int = 20_000
TRAIN_CITIZENLAB: int = 10_000

Row = tuple[str, int, str, str]


def _sha256(path: Path) -> str:
    """Calcula el SHA-256 de un archivo por bloques."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _host(url: str) -> str:
    """Extrae el host en minúsculas de una URL o de un dominio suelto."""
    candidate = url if "://" in url else f"http://{url}"
    return (urlsplit(candidate).hostname or "").lower()


def registrable_domain(url: str) -> str:
    """Devuelve el dominio registrable (eTLD+1) de una URL."""
    host = _host(url)
    return get_sld(host) or host


def _cap_per_domain(urls: list[str], per: int, rng: random.Random) -> list[str]:
    """Limita a ``per`` URLs por dominio registrable, con orden aleatorio fijo."""
    unique = list(dict.fromkeys(urls))
    rng.shuffle(unique)
    counts: Counter[str] = Counter()
    selected: list[str] = []
    for url in unique:
        domain = registrable_domain(url)
        if counts[domain] < per:
            counts[domain] += 1
            selected.append(url)
    return selected


def _read_jpcert() -> list[tuple[str, str]]:
    """Lee los CSV de JPCERT y devuelve pares ``(url, año)``."""
    rows: list[tuple[str, str]] = []
    for path in sorted((RAW_DIR / "jpcert").glob("*/*.csv")):
        year = path.parent.name
        with path.open("r", encoding="utf-8", errors="ignore", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None or "URL" not in reader.fieldnames:
                continue
            for record in reader:
                url = (record.get("URL") or "").strip()
                if url.startswith("http"):
                    rows.append((url, year))
    return rows


def _read_phishdb_links() -> list[str]:
    """Lee las URLs activas de Phishing.Database."""
    path = RAW_DIR / "phishing_links.txt"
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        return [line.strip() for line in handle if line.strip().startswith("http")]


def _read_tranco() -> list[tuple[int, str]]:
    """Lee el ranking de Tranco o, en su defecto, la alternativa zer0h."""
    tranco = RAW_DIR / "tranco.csv"
    if tranco.exists():
        rows: list[tuple[int, str]] = []
        with tranco.open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                parts = line.strip().split(",", 1)
                if len(parts) != 2:
                    continue
                try:
                    rank = int(parts[0])
                except ValueError:
                    continue
                rows.append((rank, parts[1].strip()))
        return rows

    zeroh = RAW_DIR / "zeroh_top1m.txt"
    if not zeroh.exists():
        return []
    with zeroh.open("r", encoding="utf-8", errors="ignore") as handle:
        return [(rank, line.strip()) for rank, line in enumerate(handle, start=1) if line.strip()]


def _read_citizenlab() -> list[str]:
    """Lee las URLs de la lista global de Citizen Lab."""
    path = RAW_DIR / "citizenlab_global.csv"
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", errors="ignore", newline="") as handle:
        reader = csv.DictReader(handle)
        return [
            (record.get("url") or "").strip()
            for record in reader
            if (record.get("url") or "").strip().startswith("http")
        ]


def _read_hard_negatives() -> list[str]:
    """Lee los negativos difíciles de la semilla del laboratorio."""
    if not HARD_NEGATIVES.exists():
        return []
    with HARD_NEGATIVES.open("r", encoding="utf-8", errors="ignore") as handle:
        return [line.strip() for line in handle if line.strip().startswith("http")]


def _citizenlab_paths(urls: list[str]) -> list[str]:
    """Extrae rutas y consultas legítimas reales de Citizen Lab."""
    paths: list[str] = []
    for url in urls:
        split = urlsplit(url)
        if split.path in ("", "/"):
            continue
        path = split.path + (f"?{split.query}" if split.query else "")
        paths.append(path)
    return paths


def _sample_jpcert(per_year: int, rng: random.Random) -> list[tuple[str, str]]:
    """Muestrea JPCERT de forma estratificada por año y limita 3 URLs/dominio."""
    by_year: dict[str, list[str]] = defaultdict(list)
    for url, year in _read_jpcert():
        by_year[year].append(url)

    sampled: list[tuple[str, str]] = []
    for year in sorted(by_year):
        urls = list(dict.fromkeys(by_year[year]))
        rng.shuffle(urls)
        sampled.extend((url, year) for url in urls[:per_year])

    capped = set(_cap_per_domain([url for url, _ in sampled], 3, rng))
    return [(url, year) for url, year in sampled if url in capped]


def _sample_phishdb(limit: int, rng: random.Random) -> list[str]:
    """Muestrea Phishing.Database con cap de 3 URLs por dominio."""
    urls = _cap_per_domain(_read_phishdb_links(), 3, rng)
    if len(urls) > limit:
        urls = rng.sample(urls, limit)
    return urls


def _band_negatives(
    tranco: list[tuple[int, str]],
    paths: list[str],
    rng: random.Random,
) -> list[str]:
    """Genera negativos por bandas de ranking con rutas legítimas al 50 %."""
    negatives: list[str] = []
    for start, end, count in BANDS:
        band = [domain for rank, domain in tranco if start < rank <= end]
        if not band:
            continue
        sample_size = min(count, len(band))
        for domain in rng.sample(band, sample_size):
            prefix = rng.choice(["https://", "https://www.", "http://"])
            suffix = rng.choice(paths) if paths and rng.random() < 0.5 else "/"
            negatives.append(f"{prefix}{domain}{suffix}")
    return negatives


def _build_benchmark(rng: random.Random) -> list[Row]:
    """Construye el conjunto compatible con la línea base del laboratorio."""
    rows: list[Row] = []

    for url, year in _sample_jpcert(BENCHMARK_JPCERT_PER_YEAR, rng):
        rows.append((url, 1, "jpcert", year))

    for url in _sample_phishdb(BENCHMARK_PHISHDB, rng):
        rows.append((url, 1, "phishdb", ""))

    tranco = _read_tranco()
    top10k = [domain for rank, domain in tranco if rank <= 10_000]
    for domain in rng.sample(top10k, min(BENCHMARK_TOP10K, len(top10k))):
        rows.append((f"https://{domain}", 0, "top10k", ""))

    citizenlab = _cap_per_domain(_read_citizenlab(), 3, rng)
    if len(citizenlab) > BENCHMARK_CITIZENLAB:
        citizenlab = rng.sample(citizenlab, BENCHMARK_CITIZENLAB)
    for url in citizenlab:
        rows.append((url, 0, "citizenlab", ""))

    for url in _read_hard_negatives():
        rows.append((url, 0, "hardneg", ""))

    return rows


def _build_train(rng: random.Random) -> list[Row]:
    """Construye el conjunto de entrenamiento con bandas de ranking."""
    rows: list[Row] = []

    url_year: dict[str, str] = {}
    for url, year in _read_jpcert():
        url_year.setdefault(url, year)
    jpcert = _cap_per_domain(list(url_year), 3, rng)
    if len(jpcert) > TRAIN_JPCERT:
        jpcert = rng.sample(jpcert, TRAIN_JPCERT)
    for url in jpcert:
        rows.append((url, 1, "jpcert", url_year[url]))

    for url in _sample_phishdb(TRAIN_PHISHDB, rng):
        rows.append((url, 1, "phishdb", ""))

    citizenlab = _read_citizenlab()
    paths = _citizenlab_paths(citizenlab)
    for url in _band_negatives(_read_tranco(), paths, rng):
        rows.append((url, 0, "legit", ""))

    citizenlab_capped = _cap_per_domain(citizenlab, 3, rng)
    if len(citizenlab_capped) > TRAIN_CITIZENLAB:
        citizenlab_capped = rng.sample(citizenlab_capped, TRAIN_CITIZENLAB)
    for url in citizenlab_capped:
        rows.append((url, 0, "citizenlab", ""))

    for url in _read_hard_negatives():
        rows.append((url, 0, "hardneg", ""))

    return rows


def _write_tsv(path: Path, rows: list[Row]) -> list[Row]:
    """Escribe el TSV deduplicando URLs y devuelve las filas efectivas."""
    seen: set[str] = set()
    effective: list[Row] = []
    for row in rows:
        if row[0] in seen:
            continue
        seen.add(row[0])
        effective.append(row)

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["url", "label", "source", "year"])
        writer.writerows(effective)
    return effective


def _profile_manifest(path: Path, rows: list[Row]) -> dict[str, object]:
    """Resume un perfil para el manifiesto."""
    labels = Counter(row[1] for row in rows)
    sources = Counter(row[2] for row in rows)
    return {
        "path": str(path.relative_to(ROOT)),
        "sha256": _sha256(path),
        "rows": len(rows),
        "labels": {"positivos": labels[1], "negativos": labels[0]},
        "sources": dict(sorted(sources.items())),
    }


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada del constructor de datasets."""
    parser = argparse.ArgumentParser(description="Construye los datasets del Hito 5.")
    parser.add_argument(
        "--profile",
        choices=("benchmark", "train", "both"),
        default="both",
        help="Perfil a construir (por defecto ambos).",
    )
    parser.add_argument("--seed", type=int, default=5, help="Semilla fija.")
    args = parser.parse_args(argv)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    profiles: dict[str, object] = {}
    manifest: dict[str, object] = {
        "built_at": datetime.now(UTC).isoformat(),
        "seed": args.seed,
        "profiles": profiles,
    }

    if args.profile in ("benchmark", "both"):
        rows = _write_tsv(
            PROCESSED_DIR / "benchmark.tsv",
            _build_benchmark(random.Random(args.seed)),
        )
        profiles["benchmark"] = _profile_manifest(PROCESSED_DIR / "benchmark.tsv", rows)

    if args.profile in ("train", "both"):
        rows = _write_tsv(
            PROCESSED_DIR / "dataset.tsv",
            _build_train(random.Random(args.seed)),
        )
        profiles["train"] = _profile_manifest(PROCESSED_DIR / "dataset.tsv", rows)

    manifest_path = PROCESSED_DIR / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"Manifiesto: {manifest_path.relative_to(ROOT)}")
    for name, profile in profiles.items():
        if not isinstance(profile, dict):
            continue
        print(
            f"  {name:10} rows={profile['rows']:6} "
            f"labels={profile['labels']} sources={profile['sources']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
