"""Genera la lista congelada de marcas usada por el featurizador (RF-601).

La salida es determinista: depende únicamente del contenido de
``data/raw/tranco.csv`` y de la lista manual declarada aquí.  No se escribe
ninguna marca de fecha/hora para que dos ejecuciones con el mismo ranking
produzcan exactamente el mismo archivo (RNF-108).

Uso::

    .venv/bin/python scripts/ml/gen_brands.py
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

#: Raíz del repositorio, calculada desde la ubicación del script.
ROOT: Path = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.normalization.psl import public_suffix, registrable_domain  # noqa: E402

#: Ranking Tranco (ID fijo JZW4Y) descargado en H5-T02.
TRANCO_PATH: Path = ROOT / "data" / "raw" / "tranco.csv"

#: Destino generado (artefacto de solo lectura incluido en la imagen).
OUTPUT_PATH: Path = ROOT / "app" / "engine" / "data" / "brands.py"

#: Número de dominios del ranking que alimentan la lista.
TOP_N: int = 600

#: Longitud mínima de la etiqueta derivada del ranking.
MIN_LEN: int = 5

#: Marcas añadidas explícitamente (heredadas del prototipo de laboratorio).
MANUAL_BRANDS: frozenset[str] = frozenset(
    {
        "paypal",
        "amazon",
        "apple",
        "netflix",
        "microsoft",
        "google",
        "facebook",
        "instagram",
        "whatsapp",
        "binance",
        "coinbase",
        "metamask",
        "rakuten",
        "mercari",
        "docomo",
        "softbank",
        "smbc",
        "mufg",
        "aeon",
        "epos",
        "orico",
        "jcb",
        "yamato",
        "sagawa",
        "usps",
        "dhl",
        "fedex",
        "bancolombia",
        "davivienda",
        "nequi",
        "itau",
        "bradesco",
        "santander",
        "bbva",
        "outlook",
        "office365",
        "onedrive",
        "dropbox",
        "docusign",
        "adobe",
        "steam",
        "roblox",
    }
)


def _label_from_domain(domain: str) -> str:
    """Devuelve la etiqueta registrable de ``domain`` usando la PSL vendorizada."""
    host = domain.strip().lower().rstrip(".")
    registrable = registrable_domain(host)
    suffix = public_suffix(host)
    if suffix and registrable.endswith("." + suffix):
        return registrable[: -(len(suffix) + 1)]
    return registrable


def build_brands() -> frozenset[str]:
    """Construye el conjunto de marcas a partir del ranking y la lista manual."""
    derived: set[str] = set()
    with TRANCO_PATH.open("r", encoding="utf-8") as handle:
        for index, line in enumerate(handle):
            if index >= TOP_N:
                break
            domain = line.split(",", 1)[-1].strip()
            if not domain:
                continue
            label = _label_from_domain(domain)
            if len(label) >= MIN_LEN and label.isalpha():
                derived.add(label)
    return frozenset(derived | set(MANUAL_BRANDS))


def render(brands: frozenset[str], source_sha256: str) -> str:
    """Renderiza el módulo Python congelado, ordenado y sin marcas de tiempo."""
    lines = [
        '"""Marcas congeladas para la detección de marca en lugar equivocado (RF-601).',
        "",
        "Generado por ``scripts/ml/gen_brands.py``. NO EDITAR A MANO.",
        "",
        f"Fuente: top {TOP_N} de Tranco (ID JZW4Y) + lista manual de laboratorio.",
        "Se usa la PSL vendorizada (RF-501), no ``publicsuffix2``.",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        'BRANDS_VERSION: str = "v1"',
        f'SOURCE_SHA256: str = "{source_sha256}"',
        f"TOP_N: int = {TOP_N}",
        f"MIN_LEN: int = {MIN_LEN}",
        "",
        "# Ordenado para que la salida sea byte-a-byte reproducible.",
        "BRANDS: frozenset[str] = frozenset(",
        "    {",
    ]
    lines.extend(f'        "{brand}",' for brand in sorted(brands))
    lines.extend(
        [
            "    }",
            ")",
            "",
            '__all__ = ["BRANDS", "BRANDS_VERSION", "SOURCE_SHA256", "TOP_N", "MIN_LEN"]',
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    """Genera ``app/engine/data/brands.py`` y reporta el resultado."""
    source_sha256 = hashlib.sha256(TRANCO_PATH.read_bytes()).hexdigest()
    brands = build_brands()
    OUTPUT_PATH.write_text(render(brands, source_sha256), encoding="utf-8")
    print(f"Marcas generadas: {len(brands)}")
    print(f"Archivo: {OUTPUT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
