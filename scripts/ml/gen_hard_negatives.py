"""Genera ``tests/data/hard_negatives.txt`` (RF-606).

Parte de la semilla de 48 URLs reales del laboratorio y añade URLs sintéticas
de login/seguridad sobre el top-1000 de Tranco.  La salida es determinista:
mismo ranking y mismas plantillas producen exactamente el mismo archivo.

Uso::

    .venv/bin/python scripts/ml/gen_hard_negatives.py
"""

from __future__ import annotations

import hashlib
from pathlib import Path

ROOT: Path = Path(__file__).resolve().parents[2]
TRANCO_PATH: Path = ROOT / "data" / "raw" / "tranco.csv"
SEED_PATH: Path = ROOT / "docs" / "specs" / "accuracy-lab" / "data" / "hard_negatives_seed.txt"
OUTPUT_PATH: Path = ROOT / "tests" / "data" / "hard_negatives.txt"

TOP_DOMAINS: int = 1000
PER_DOMAIN: int = 3

#: Plantillas legítimas de autenticación, seguridad y soporte.
TEMPLATES: tuple[str, ...] = (
    "/login",
    "/signin",
    "/account/verify?token=example",
    "/security",
    "/oauth2/authorize?response_type=code&client_id=example",
    "/customer/support/login",
)


def _seed_urls() -> list[str]:
    """Lee las 48 URLs difíciles reales del laboratorio."""
    return [
        line.strip() for line in SEED_PATH.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def build() -> list[str]:
    """Construye la lista completa sin duplicados y en orden determinista."""
    urls: list[str] = []
    seen: set[str] = set()
    for url in _seed_urls():
        if url not in seen:
            seen.add(url)
            urls.append(url)

    domains: list[str] = []
    with TRANCO_PATH.open("r", encoding="utf-8") as handle:
        for index, line in enumerate(handle):
            if index >= TOP_DOMAINS:
                break
            domain = line.split(",", 1)[-1].strip().lower().rstrip(".")
            if domain and "." in domain and domain not in domains:
                domains.append(domain)

    for position, domain in enumerate(domains):
        for offset in range(PER_DOMAIN):
            template = TEMPLATES[(position + offset) % len(TEMPLATES)]
            url = f"https://{domain}{template}"
            if url not in seen:
                seen.add(url)
                urls.append(url)
    return urls


def main() -> None:
    """Escribe el archivo y reporta conteo y SHA-256."""
    urls = build()
    content = "\n".join(urls) + "\n"
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(content, encoding="utf-8")
    print(f"Negativos difíciles: {len(urls)}")
    print(f"SHA-256: {hashlib.sha256(content.encode('utf-8')).hexdigest()}")
    print(f"Archivo: {OUTPUT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
