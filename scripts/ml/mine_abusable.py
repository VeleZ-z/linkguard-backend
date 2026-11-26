"""mine_abusable: detecta dominios registrables con muchas URLs de phishing.

Para cada dominio registrable de la allowlist (top-100k Tranco), cuenta URLs de
phishing en Phishing.Database + OpenPhish (+ JPCERT si está disponible) y
vuelca a docs/reports/abusable-candidates.tsv los que tengan >= 20.

Usa como punto de partida docs/specs/accuracy-lab/abusable-candidates.tsv.
"""

from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

# Asegurar que ``app`` sea importable.
ROOT: Path = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.normalization.psl import registrable_domain  # noqa: E402

# Rutas.
PHISHDB_LINKS: Path = ROOT / "data" / "raw" / "phishing_links.txt"
OPENPHISH_FEED: Path | None = None  # Se descarga en runtime; aquí usamos vacío
JPCERT_DIR: Path = ROOT / "data" / "raw" / "jpcert"
ALLOWLIST: Path = ROOT / "app" / "engine" / "data" / "allowlist_top100k.txt"
TSV_SEED: Path = ROOT / "docs" / "specs" / "accuracy-lab" / "abusable-candidates.tsv"
TSV_OUT: Path = ROOT / "docs" / "reports" / "abusable-candidates.tsv"

THRESHOLD: int = 20


def _load_jpcert_urls() -> Counter[str]:
    """Carga URLs de JPCERT si el directorio existe."""
    counts: Counter[str] = Counter()
    if not JPCERT_DIR.exists():
        return counts
    for year_dir in sorted(JPCERT_DIR.iterdir()):
        if not year_dir.is_dir():
            continue
        for csv_file in year_dir.glob("*.csv"):
            try:
                with csv_file.open("r", encoding="utf-8", errors="replace") as f:
                    reader = csv.reader(f)
                    header = next(reader, None)
                    if header is None:
                        continue
                    # Buscar columna de URL
                    url_idx = None
                    for i, col in enumerate(header):
                        if "url" in col.lower():
                            url_idx = i
                            break
                    if url_idx is None:
                        continue
                    for row in reader:
                        if len(row) <= url_idx:
                            continue
                        url = row[url_idx].strip()
                        if not url:
                            continue
                        try:
                            rd = registrable_domain(urlparse(url).netloc or url)
                            if rd:
                                counts[rd] += 1
                        except Exception:
                            pass
            except Exception:
                pass
    return counts


def _load_phishdb_counts() -> Counter[str]:
    """Cuenta URLs de phishing por dominio registrable en Phishing.Database."""
    counts: Counter[str] = Counter()
    if not PHISHDB_LINKS.exists():
        return counts
    with PHISHDB_LINKS.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line or not line.startswith(("http://", "https://", "ftp://")):
                continue
            try:
                parsed = urlparse(line)
                netloc = parsed.netloc
                if not netloc:
                    continue
                rd = registrable_domain(netloc)
                if rd:
                    counts[rd] += 1
            except Exception:
                pass
    return counts


def _load_allowlist_domains() -> set[str]:
    """Carga los dominios de la allowlist."""
    domains: set[str] = set()
    if not ALLOWLIST.exists():
        return domains
    with ALLOWLIST.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip().lower()
            if line:
                domains.add(line)
    return domains


def _load_seed_tsv() -> dict[str, dict[str, str]]:
    """Carga el TSV semilla como diccionario claveado por dominio."""
    seed: dict[str, dict[str, str]] = {}
    if not TSV_SEED.exists():
        return seed
    with TSV_SEED.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            dom = row.get("dominio_registrable", "").strip().lower()
            if dom:
                seed[dom] = row
    return seed


def main() -> None:
    """Punto de entrada principal."""
    jpcert_counts = _load_jpcert_urls()
    phishdb_counts = _load_phishdb_counts()
    allowlist_domains = _load_allowlist_domains()
    seed = _load_seed_tsv()

    # Combinar conteos: phishdb + jpcert (openphish vacío en build offline)
    combined: Counter[str] = Counter()
    for dom, cnt in phishdb_counts.items():
        combined[dom] += cnt
    for dom, cnt in jpcert_counts.items():
        combined[dom] += cnt

    # Filtrar solo dominios de la allowlist con >= THRESHOLD
    candidates: list[dict[str, str]] = []
    for dom in sorted(allowlist_domains):
        total = combined.get(dom, 0)
        if total >= THRESHOLD:
            seed_row = seed.get(dom, {})
            candidates.append(
                {
                    "dominio_registrable": dom,
                    "rank_top100k": seed_row.get("rank_top100k", ""),
                    "phishing_jpcert": str(jpcert_counts.get(dom, 0)),
                    "phishing_phishdb": str(phishdb_counts.get(dom, 0)),
                    "total": str(total),
                    "hosts_distintos": seed_row.get("hosts_distintos", ""),
                    "top3_hosts": seed_row.get("top3_hosts", ""),
                }
            )

    # Escribir TSV de salida
    TSV_OUT.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "dominio_registrable",
        "rank_top100k",
        "phishing_jpcert",
        "phishing_phishdb",
        "total",
        "hosts_distintos",
        "top3_hosts",
    ]
    with TSV_OUT.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        for row in candidates:
            writer.writerow(row)

    print(f"✔ mine_abusable: {len(candidates)} candidatos con >={THRESHOLD} URLs")
    print(f"✔ Escrito en {TSV_OUT}")


if __name__ == "__main__":
    main()
