"""Descarga las fuentes de datos del laboratorio de accuracy (H5-T02).

Uso::

    python scripts/ml/fetch_data.py [--force] [--years 2019 2020 ...]

Fuentes descargadas:

* JPCERT/CC ``phishurl-list`` (un CSV por mes, agrupado por año).
* ``mitchellkrogza/Phishing.Database`` (URLs y dominios activos).
* Tranco con ID de lista fijo; si no está disponible se usa como alternativa
  documentada ``zer0h/top-1000000-domains``.
* ``citizenlab/test-lists`` (``lists/global.csv``).

Los archivos se guardan en ``data/raw/`` (ignorado por git) y se escribe
``data/raw/manifest.json`` con fecha, conteos y SHA-256. El script no se
importa desde ``app/`` y solo descarga fuentes públicas de laboratorio: no
contacta ninguna URL analizada (RNF-101).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

ROOT: Path = Path(__file__).resolve().parents[2]
RAW_DIR: Path = ROOT / "data" / "raw"

JPCERT_API: str = "https://api.github.com/repos/JPCERTCC/phishurl-list/contents"
PHISHDB_LINKS: str = (
    "https://raw.githubusercontent.com/mitchellkrogza/Phishing.Database/"
    "master/phishing-links-ACTIVE.txt"
)
PHISHDB_DOMAINS: str = (
    "https://raw.githubusercontent.com/mitchellkrogza/Phishing.Database/"
    "master/phishing-domains-ACTIVE.txt"
)
TRANCO_LIST_ID: str = "JZW4Y"
TRANCO_URL: str = f"https://tranco-list.eu/download/{TRANCO_LIST_ID}/1000000"
ZEROH_URL: str = (
    "https://raw.githubusercontent.com/zer0h/top-1000000-domains/master/top-1000000-domains"
)
CITIZENLAB_URL: str = (
    "https://raw.githubusercontent.com/citizenlab/test-lists/master/lists/global.csv"
)
DEFAULT_YEARS: tuple[int, ...] = tuple(range(2019, 2027))
USER_AGENT: str = "linkguard-accuracy-lab/1.0"


def _sha256(path: Path) -> str:
    """Calcula el SHA-256 de un archivo por bloques."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _count_text_lines(path: Path, *, prefix: str | None = None) -> int:
    """Cuenta líneas no vacías, opcionalmente solo las que empiezan por ``prefix``."""
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        if prefix is None:
            return sum(1 for line in handle if line.strip())
        return sum(1 for line in handle if line.strip().startswith(prefix))


def _count_csv_rows(path: Path, *, column: str = "URL") -> int:
    """Cuenta filas de un CSV con la columna indicada no vacía."""
    with path.open("r", encoding="utf-8", errors="ignore", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or column not in reader.fieldnames:
            return 0
        return sum(1 for row in reader if (row.get(column) or "").strip())


def _download(
    client: httpx.Client,
    url: str,
    dest: Path,
    *,
    force: bool,
    counter: Callable[[Path], int] | None = None,
) -> dict[str, Any]:
    """Descarga ``url`` en ``dest`` y devuelve metadatos verificables.

    Un fallo de red no interrumpe la ejecución: se devuelve ``status="error"``
    para que el manifiesto documente la fuente no disponible.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and not force:
        status = "cached"
    else:
        try:
            response = client.get(url)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            return {"url": url, "status": "error", "error": type(exc).__name__}
        dest.write_bytes(response.content)
        status = "ok"

    item: dict[str, Any] = {
        "url": url,
        "status": status,
        "path": str(dest.relative_to(ROOT)),
        "bytes": dest.stat().st_size,
        "sha256": _sha256(dest),
    }
    if counter is not None:
        item["records"] = counter(dest)
    return item


def _fetch_jpcert(
    client: httpx.Client,
    years: tuple[int, ...],
    *,
    force: bool,
) -> dict[str, Any]:
    """Descarga los CSV mensuales de JPCERT para los años indicados."""
    source: dict[str, Any] = {"status": "ok", "files": [], "years": {}, "records": 0}
    for year in years:
        listing_url = f"{JPCERT_API}/{year}"
        try:
            response = client.get(listing_url)
            response.raise_for_status()
            entries = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            source["status"] = "partial"
            source["years"][str(year)] = {
                "status": "error",
                "error": type(exc).__name__,
            }
            continue

        year_records = 0
        year_files = 0
        for entry in entries:
            name = entry.get("name", "")
            download_url = entry.get("download_url")
            if not name.endswith(".csv") or not download_url:
                continue
            dest = RAW_DIR / "jpcert" / str(year) / name
            item = _download(
                client,
                download_url,
                dest,
                force=force,
                counter=_count_csv_rows,
            )
            item["year"] = year
            source["files"].append(item)
            year_files += 1
            if item["status"] == "error":
                source["status"] = "partial"
            else:
                year_records += int(item.get("records") or 0)

        source["years"][str(year)] = {"files": year_files, "records": year_records}
        source["records"] += year_records
    return source


def _fetch_phishing_database(client: httpx.Client, *, force: bool) -> dict[str, Any]:
    """Descarga las listas activas de URLs y dominios de Phishing.Database."""
    links = _download(
        client,
        PHISHDB_LINKS,
        RAW_DIR / "phishing_links.txt",
        force=force,
        counter=lambda path: _count_text_lines(path, prefix="http"),
    )
    domains = _download(
        client,
        PHISHDB_DOMAINS,
        RAW_DIR / "phishing_domains.txt",
        force=force,
        counter=_count_text_lines,
    )
    files = [links, domains]
    status = "ok" if all(item["status"] != "error" for item in files) else "partial"
    return {
        "status": status,
        "files": files,
        "records": sum(int(item.get("records") or 0) for item in files),
    }


def _fetch_tranco(client: httpx.Client, *, force: bool) -> dict[str, Any]:
    """Descarga Tranco con ID fijo; si falla, usa la alternativa zer0h."""
    item = _download(
        client,
        TRANCO_URL,
        RAW_DIR / "tranco.csv",
        force=force,
        counter=_count_text_lines,
    )
    if item["status"] != "error":
        item["list_id"] = TRANCO_LIST_ID
        return {
            "status": "ok",
            "source": "tranco",
            "list_id": TRANCO_LIST_ID,
            "files": [item],
            "records": int(item.get("records") or 0),
        }

    fallback = _download(
        client,
        ZEROH_URL,
        RAW_DIR / "zeroh_top1m.txt",
        force=force,
        counter=_count_text_lines,
    )
    fallback["source"] = "zer0h/top-1000000-domains"
    status = "fallback" if fallback["status"] != "error" else "error"
    return {
        "status": status,
        "source": "zer0h",
        "list_id": None,
        "files": [fallback],
        "records": int(fallback.get("records") or 0),
        "note": (
            "Tranco no disponible; se usó zer0h/top-1000000-domains como alternativa documentada."
        ),
    }


def _fetch_citizenlab(client: httpx.Client, *, force: bool) -> dict[str, Any]:
    """Descarga la lista global de Citizen Lab (rutas legítimas reales)."""
    item = _download(
        client,
        CITIZENLAB_URL,
        RAW_DIR / "citizenlab_global.csv",
        force=force,
        counter=lambda path: _count_csv_rows(path, column="url"),
    )
    return {
        "status": "ok" if item["status"] != "error" else "error",
        "files": [item],
        "records": int(item.get("records") or 0),
    }


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada del descargador de fuentes."""
    parser = argparse.ArgumentParser(
        description="Descarga las fuentes del laboratorio de accuracy."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Vuelve a descargar aunque el archivo exista.",
    )
    parser.add_argument(
        "--years",
        nargs="+",
        type=int,
        default=list(DEFAULT_YEARS),
        help="Años de JPCERT a descargar (por defecto 2019-2026).",
    )
    args = parser.parse_args(argv)

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    with httpx.Client(
        timeout=120.0,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        sources = {
            "jpcert": _fetch_jpcert(client, tuple(args.years), force=args.force),
            "phishing_database": _fetch_phishing_database(client, force=args.force),
            "tranco": _fetch_tranco(client, force=args.force),
            "citizenlab": _fetch_citizenlab(client, force=args.force),
        }

    manifest = {
        "fetched_at": datetime.now(UTC).isoformat(),
        "tranco_list_id": TRANCO_LIST_ID,
        "sources": sources,
    }
    manifest_path = RAW_DIR / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"Manifiesto: {manifest_path.relative_to(ROOT)}")
    for name, source in sources.items():
        print(f"  {name:18} status={source['status']:<8} records={source.get('records', 0)}")

    available = sum(1 for source in sources.values() if source["status"] != "error")
    return 0 if available else 1


if __name__ == "__main__":
    raise SystemExit(main())
