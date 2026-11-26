"""H5-T05: Generador de artefactos de reputación.

Crea:
 - Artefactos de allowlist (top-100k Tranco, excluidos sufijos públicos y servicios abusables).
 - ``app/engine/data/abusable_services.py`` con la semilla RF-503.
 - Blocklists binarios (blake2b 8 bytes) y manifiesto ``manifest.json``.
 - Fuentes: Phishing.Database, OpenPhish, URLhaus, PhishTank (opcional).

El tamaño total de los artefactos debe ser ≤ 15 MB.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

# Asegurar que ``app`` sea importable.
ROOT: Path = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.engine.data.url_shorteners import URL_SHORTENERS  # noqa: E402
from app.normalization.psl import PSL  # noqa: E402
from app.reputation.canonical import canonical_url_key  # noqa: E402

# Rutas relativas al proyecto.
DATA_DIR: Path = ROOT / "app" / "engine" / "data"
BLOCKLIST_DIR: Path = DATA_DIR / "blocklist"
MANIFEST_PATH: Path = BLOCKLIST_DIR / "manifest.json"

ABUSABLE_SERVICES_PATH: Path = DATA_DIR / "abusable_services.py"
ALLOWLIST_PATH: Path = DATA_DIR / "allowlist_top100k.txt"
MODEL_PATH: Path = DATA_DIR / "model_v1.json"

#: Tope total del conjunto de artefactos (incluye el modelo, RNF-107).
MAX_TOTAL_BYTES: int = 15 * 1024 * 1024
#: Límites de cualquier descarga de feed realizada en CI (RF-505).
MAX_FEED_BYTES: int = 64 * 1024 * 1024
MAX_FEED_REDIRS: int = 3


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _blake2b_8bytes(value: bytes) -> bytes:
    """Devuelve los primeros 8 bytes (big-endian) de un hash blake2b."""
    return hashlib.blake2b(value, digest_size=8).digest()


# ---------------------------------------------------------------------------
# 1) Allowlist top-100k de Tranco (ID fijo JZW4Y)
# ---------------------------------------------------------------------------


def _download_tranco_top100k() -> list[str]:
    """Descarga el ranking de Tranco (ID fijo JZW4Y) y devuelve las 100 000 primeras dominios."""
    url = "https://tranco-list.eu/download/JZW4Y/1000000"
    try:
        result = subprocess.run(
            [
                "curl",
                "-sS",
                "-L",
                "--fail",
                "--max-redirs",
                str(MAX_FEED_REDIRS),
                "--max-filesize",
                str(MAX_FEED_BYTES),
                "-m",
                "60",
                url,
            ],
            capture_output=True,
            timeout=120,
        )
        if result.returncode != 0:
            print("⚠ No se pudo descargar Tranco; se usará lista vacía.", file=sys.stderr)
            return []
        text = result.stdout.decode("utf-8", errors="replace")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        domains: list[str] = []
        for line in lines:
            parts = line.split(",", 1)
            if len(parts) == 2:
                domains.append(parts[1].strip())
            else:
                domains.append(parts[0].strip())
        return domains[:100_000]
    except Exception as exc:  # pragma: no cover - fallo de red
        print(f"⚠ Error accediendo a Tranco: {exc}", file=sys.stderr)
        return []


def _load_psl_suffixes_set() -> set[str]:
    """Carga el conjunto de sufijos públicos de la PSL vendorizada (O(1) lookup)."""
    suffixes: set[str] = set()
    for line in PSL._lines:
        suf = line.lstrip(".")
        if suf:
            suffixes.add(suf.lower())
    return suffixes


def _is_public_suffix(domain: str, psl_suffixes: set[str]) -> bool:
    """Devuelve True si el dominio ES un sufijo público (p.ej. com, co.uk, vercel.app, github.io).

    Solo excluimos dominios que SON sufijos públicos, no dominios que residen
    bajo un sufijo público (p.ej. ``a.vercel.app`` NO se excluye).
    """
    return domain.lower() in psl_suffixes


def _is_abusable(domain: str, abusable_patterns: list[str]) -> bool:
    """Devuelve True si el dominio coincide con algún patrón abusable."""
    for pattern in abusable_patterns:
        if "*" in pattern:
            pat = pattern.replace(".", r"\.").replace("*", ".*")
            if re.search(pat, domain):
                return True
        else:
            if domain == pattern or domain.endswith("." + pattern):
                return True
    return False


def _is_shortener_or_ddns(domain: str) -> bool:
    """Devuelve True si el dominio es un acortador (F05) o servicio DDNS."""
    d = domain.lower()
    # Acortadores conocidos (lista F05): dominio exacto o subdominio
    for s in URL_SHORTENERS:
        if d == s or d.endswith("." + s):
            return True
    # Servicios DDNS dinámicos
    ddns_patterns = [
        "duckdns.org",
        "no-ip.org",
        "ddns.net",
        "dynu.net",
        "dnsomatic.com",
        "freedynamicdns.org",
        "hopto.org",
        "ddnsfree.com",
        "static.cl",
        "servebeer.com",
    ]
    for p in ddns_patterns:
        if d == p or d.endswith("." + p):
            return True
    return False


def _build_allowlist(
    top100k_domains: list[str], psl_suffixes: set[str], abusable_patterns: list[str]
) -> tuple[set[str], dict[str, Any]]:
    """Construye la allowlist: dominios registrables del top-100k, sin sufijos públicos, abusables, acortadores ni DDNS.

    Retorna (allowlist, stats) donde stats tiene conteos y muestras de excluidos.
    """
    allowlist: set[str] = set()
    psl_excluded_list: list[str] = []
    abusable_excluded_list: list[str] = []
    shortener_ddns_excluded_list: list[str] = []

    for domain in top100k_domains:
        if _is_public_suffix(domain, psl_suffixes):
            psl_excluded_list.append(domain.lower())
            continue
        if _is_abusable(domain.lower(), abusable_patterns):
            abusable_excluded_list.append(domain.lower())
            continue
        if _is_shortener_or_ddns(domain.lower()):
            shortener_ddns_excluded_list.append(domain.lower())
            continue
        allowlist.add(domain.lower())

    stats: dict[str, Any] = {
        "total_read": len(top100k_domains),
        "psl_excluded": len(psl_excluded_list),
        "abusable_excluded": len(abusable_excluded_list),
        "shortener_ddns_excluded": len(shortener_ddns_excluded_list),
        "final_count": len(allowlist),
        "psl_excluded_first10": psl_excluded_list[:10],
        "abusable_excluded_first10": abusable_excluded_list[:10],
        "shortener_ddns_excluded_first10": shortener_ddns_excluded_list[:10],
        "allowlist_first10": sorted(allowlist)[:10],
    }
    return allowlist, stats


# ---------------------------------------------------------------------------
# 2) Abusable services (RF-503)
# ---------------------------------------------------------------------------


def _write_abusable_services(path: Path, allowlist_hosts: set[str]) -> tuple[list[str], list[str]]:
    """Escribe app/engine/data/abusable_services.py con la semilla RF-503.

    Reglas de emparejamiento:
      - Patrón sin "/": coincide si el host es igual al patrón o si el host
        termina con "." + patrón (sufijo en límite de etiqueta).
        Ejemplo: "web.app" coincide con "x.web.app" pero NO con "evilweb.app".
      - Patrón con "/": coincide si el host base (host == base o host termina
        en "." + base) y la ruta empieza con el prefijo.
        Ejemplo: "dropbox.com/s/" coincide con "x.dropbox.com/s/abc" y con
        "dropbox.com/s/abc", pero NO con "dropbox.com/pricing".
    """
    services = [
        "docs.google.com",
        "drive.google.com",
        "sites.google.com",
        "forms.gle",
        "forms.office.com",
        "storage.googleapis.com",
        "s3.amazonaws.com",
        "notion.site",
        "firebaseapp.com",
        "web.app",
        "dropbox.com/s/",
        "duckdns.org",
        "no-ip.org",
        "ddns.net",
    ]

    # Agregar candidatos cuyo dominio (o subdominio) esté en la allowlist,
    # para que no se escapen del blocklist por estar allowlisteados.
    added: list[str] = []
    allowlist_lower = {d.lower() for d in allowlist_hosts}
    for domain in sorted(allowlist_lower):
        for s in services:
            pattern = s.lstrip(".").lower()
            if "/" in pattern:
                host_base = pattern.split("/")[0]
                # Si el host base del patrón de ruta está en la allowlist,
                # agregar el host base como patrón completo.
                if domain == host_base or domain.endswith("." + host_base):
                    if host_base not in services:
                        services.append(host_base)
                        added.append(host_base)
                    break
            else:
                if domain == pattern or domain.endswith("." + pattern):
                    if pattern not in services:
                        services.append(pattern)
                        added.append(pattern)
                    break

    lines: list[str] = []
    lines.append("# Bloque de servicios considerados abusables (RF-503).")
    lines.append("# Cada elemento es un patrón de host o un host con prefijo de ruta '/'.")
    lines.append("#")
    lines.append("# Reglas de emparejamiento:")
    lines.append('# - Patrón sin "/": coincide si host == patrón o host termina con "." + patrón')
    lines.append(
        '#   (límite de etiqueta). Ej.: "web.app" coincide con "x.web.app", no con "evilweb.app".'
    )
    lines.append(
        '# - Patrón con "/": coincide si el host base (host == base o termina en "." + base)'
    )
    lines.append(
        '#   y la ruta empieza con el prefijo. Ej.: "dropbox.com/s/" coincide con "dropbox.com/s/abc"'
    )
    lines.append('#   y con "x.dropbox.com/s/abc", no con "dropbox.com/pricing".')
    lines.append("")
    lines.append("")
    lines.append("def _matches_abusable(host_or_url: str) -> bool:")
    lines.append('    """Devuelve True si ``host_or_url`` coincide con algún patrón abusable.')
    lines.append("")
    lines.append("    Reglas:")
    lines.append('    - Patrón sin "/": host == patrón o host termina con "." + patrón.')
    lines.append(
        '    - Patrón con "/": el host base (host == base o termina en "." + base) y la ruta'
    )
    lines.append("      empieza con el prefijo.")
    lines.append('    """')
    lines.append("    value = host_or_url.lower()")
    lines.append("    for pat in ABUSABLE_SERVICES:")
    lines.append('        if "/" in pat:')
    lines.append('            base, prefix = pat.split("/", 1)')
    lines.append('            host = value.split("/", 1)[0]')
    lines.append('            path = value.split("/", 1)[1] if "/" in value else ""')
    lines.append(
        '            if (host == base or host.endswith("." + base)) and path.startswith(prefix):'
    )
    lines.append("                return True")
    lines.append("        else:")
    lines.append('            if value == pat or value.endswith("." + pat):')
    lines.append("                return True")
    lines.append("    return False")
    lines.append("")
    lines.append("ABUSABLE_SERVICES: tuple[str, ...] = (")
    for s in services:
        lines.append(f'    "{s}",')
    lines.append(")")
    lines.append("")
    lines.append('__all__ = ["ABUSABLE_SERVICES", "_matches_abusable"]')
    content = "\n".join(lines) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"✔ Se escribió {path}")
    if added:
        print(f"✔ Candidatos añadidos por coincidencia con allowlist: {added}")
    return services, added


# ---------------------------------------------------------------------------
# 3) Blocklists (blake2b 8 bytes) y manifiesto
# ---------------------------------------------------------------------------


def _normalize_host(host: str) -> str:
    """Normaliza un host: minúsculas, sin puerto, sin ruta."""
    host = host.lower()
    if "/" in host:
        host = host[: host.index("/")]
    if ":" in host:
        host = host[: host.index(":")]
    return host


def build_artifacts() -> dict[str, Any]:
    """Punto de entrada principal: construye todos los artefactos de reputación."""
    manifest: dict[str, Any] = {
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "sources": {},
        "errors": [],
        "total_size_mb": 0.0,
    }

    # Cargar sufijos públicos de la PSL (una sola vez).
    psl_suffixes: set[str] = _load_psl_suffixes_set()

    # --- 1) Allowlist top-100k Tranco ---
    # Usar archivo local data/raw/tranco.csv (ya descargado en H5-T02).
    tranco_path = ROOT / "data" / "raw" / "tranco.csv"
    if tranco_path.exists():
        tranco_domains: list[str] = []
        with tranco_path.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                parts = line.strip().split(",", 1)
                if len(parts) == 2:
                    tranco_domains.append(parts[1].strip())
        tranco_domains = tranco_domains[:100_000]
    else:
        # Fallback: descargar
        tranco_domains = _download_tranco_top100k()

    # Cargar patrones abusable desde ABUSABLE_SERVICES
    abusable_patterns: list[str] = []
    try:
        from app.engine.data.abusable_services import ABUSABLE_SERVICES  # type: ignore

        abusable_patterns = list(ABUSABLE_SERVICES)
    except Exception:
        print(
            "⚠ No se pudo cargar ABUSABLE_SERVICES; se procederá sin filtrado abusable.",
            file=sys.stderr,
        )

    allowlist, allowlist_stats = _build_allowlist(tranco_domains, psl_suffixes, abusable_patterns)
    ALLOWLIST_PATH.write_text("\n".join(sorted(allowlist)), encoding="utf-8")
    manifest["sources"]["allowlist"] = {
        "type": "tranco_top100k",
        "count": len(allowlist),
        "total_read": allowlist_stats["total_read"],
        "psl_excluded": allowlist_stats["psl_excluded"],
        "abusable_excluded": allowlist_stats["abusable_excluded"],
        "shortener_ddns_excluded": allowlist_stats["shortener_ddns_excluded"],
        "psl_excluded_first10": allowlist_stats["psl_excluded_first10"],
        "abusable_excluded_first10": allowlist_stats["abusable_excluded_first10"],
        "shortener_ddns_excluded_first10": allowlist_stats["shortener_ddns_excluded_first10"],
        "allowlist_first10": allowlist_stats["allowlist_first10"],
        "path": str(ALLOWLIST_PATH.relative_to(ROOT)),
        "sha256": _sha256(ALLOWLIST_PATH),
    }
    print(
        f"✔ Allowlist: leídos={allowlist_stats['total_read']}, PSL_excl={allowlist_stats['psl_excluded']}, "
        f"abus_excl={allowlist_stats['abusable_excluded']}, shortener/ddns_excl={allowlist_stats['shortener_ddns_excluded']}, "
        f"finales={allowlist_stats['final_count']}"
    )
    if allowlist_stats["final_count"] < 50_000:
        raise RuntimeError(
            f"Allowlist demasiado pequeña: {allowlist_stats['final_count']} (< 50000)"
        )

    # --- 2) Abusable services ---
    abusable_services_list, abusable_added = _write_abusable_services(
        ABUSABLE_SERVICES_PATH, allowlist
    )
    # Recargar patrones desde el archivo recién escrito (incluye candidatos de allowlist)
    try:
        from app.engine.data.abusable_services import ABUSABLE_SERVICES as _SERV  # type: ignore

        abusable_patterns = list(_SERV)
        ab_count = len(_SERV)
    except Exception:
        ab_count = 0
    manifest["sources"]["abusable_services"] = {
        "type": "rf503_seed",
        "count": ab_count,
        "path": str(ABUSABLE_SERVICES_PATH.relative_to(ROOT)),
    }
    print("✔ Se escribió abusable_services.py")
    if abusable_added:
        print(f"✔ Candidatos añadidos por coincidencia con allowlist: {abusable_added}")

    # --- 3) Blocklists (sin filtro de allowlist en el artefacto; coincidencia exacta de feed gana, RF-803) ---
    blocklist_uris: set[bytes] = set()
    blocklist_hosts: set[bytes] = set()

    def _host_is_abusable(host: str) -> bool:
        """Chequea si el host coincide con algún patrón abusable."""
        return _is_abusable(host, abusable_patterns)

    def _add_uri(key: str, counters: dict[str, int]) -> None:
        """Añade una clave canónica de URL al blocklist de URLs (deduplicado por hash)."""
        if not key:
            counters["invalid"] += 1
            return
        host = key.split("/", 1)[0]
        # Chequeo de abusables ANTES de cualquier otro filtro
        if _host_is_abusable(host):
            blocklist_uris.add(_blake2b_8bytes(key.encode("utf-8")))
            return
        blocklist_uris.add(_blake2b_8bytes(key.encode("utf-8")))

    def _add_host(host: str, counters: dict[str, int]) -> None:
        """Añade un host al blocklist de hosts (deduplicado por hash)."""
        host = host.lower()
        if not host:
            counters["invalid"] += 1
            return
        if _host_is_abusable(host):
            blocklist_hosts.add(_blake2b_8bytes(host.encode("utf-8")))
            return
        blocklist_hosts.add(_blake2b_8bytes(host.encode("utf-8")))

    # Phishing.Database (links y dominios)
    phishdb_links_path = ROOT / "data" / "raw" / "phishing_links.txt"
    phishdb_domains_path = ROOT / "data" / "raw" / "phishing_domains.txt"

    links_counters = {"read": 0, "invalid": 0, "duplicates": 0}
    hosts_counters = {"read": 0, "invalid": 0, "duplicates": 0}

    if phishdb_links_path.exists():
        with phishdb_links_path.open("r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    links_counters["invalid"] += 1
                    continue
                links_counters["read"] += 1
                if not line.startswith(("http://", "https://", "ftp://")):
                    links_counters["invalid"] += 1
                    continue
                try:
                    key = canonical_url_key(line)
                    _add_uri(key, links_counters)
                except Exception:
                    links_counters["invalid"] += 1

    if phishdb_domains_path.exists():
        with phishdb_domains_path.open("r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    hosts_counters["invalid"] += 1
                    continue
                hosts_counters["read"] += 1
                host = line.lower()
                if "/" in host:
                    host = host[: host.index("/")]
                if ":" in host:
                    host = host[: host.index(":")]
                if host:
                    _add_host(host, hosts_counters)

    links_duplicates = links_counters["read"] - links_counters["invalid"] - len(blocklist_uris)
    hosts_duplicates = hosts_counters["read"] - hosts_counters["invalid"] - len(blocklist_hosts)

    manifest["sources"]["phishing_database"] = {
        "type": "phishing_links",
        "status": "ok",
        "records_read": links_counters["read"],
        "records_invalid": links_counters["invalid"],
        "records_duplicates": max(0, links_duplicates),
        "records_skipped": 0,
        "records_final": len(blocklist_uris),
        "hosts_read": hosts_counters["read"],
        "hosts_invalid": hosts_counters["invalid"],
        "hosts_duplicates": max(0, hosts_duplicates),
        "hosts_skipped": 0,
        "hosts_final": len(blocklist_hosts),
        "path": str(phishdb_links_path.relative_to(ROOT)),
    }
    # Reconciliación por fuente: leídas - inválidas - duplicadas - saltadas = finales
    links_reconciled = (
        links_counters["read"] - links_counters["invalid"] - max(0, links_duplicates) - 0
    )
    hosts_reconciled = (
        hosts_counters["read"] - hosts_counters["invalid"] - max(0, hosts_duplicates) - 0
    )
    if links_reconciled != len(blocklist_uris) or hosts_reconciled != len(blocklist_hosts):
        raise RuntimeError(
            "Reconciliación de phishing_database falló: "
            f"links {links_reconciled} != {len(blocklist_uris)}, "
            f"hosts {hosts_reconciled} != {len(blocklist_hosts)}"
        )

    # OpenPhish community feed (descargar si está disponible)
    openphish_url = "https://raw.githubusercontent.com/openphish/public_feed/main/feed.txt"
    openphish_data = None
    try:
        result = subprocess.run(
            [
                "curl",
                "-sS",
                "-L",
                "--fail",
                "--max-redirs",
                str(MAX_FEED_REDIRS),
                "--max-filesize",
                str(MAX_FEED_BYTES),
                "-m",
                "30",
                "-w",
                "%{http_code}",
                openphish_url,
            ],
            capture_output=True,
            timeout=40,
        )
        if result.returncode != 0:
            raise RuntimeError(f"curl falló con código {result.returncode}")
        openphish_http_code = int(result.stdout.decode("utf-8", errors="replace").strip()[-3:])
        openphish_data = result.stdout
    except Exception:
        openphish_http_code = None

    openphish_size = None
    openphish_first_bytes = None

    if openphish_data:
        try:
            text = openphish_data.decode("utf-8", errors="replace")
            urls: list[str] = []
            hosts: list[str] = []
            for line in text.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                urls.append(line)
                try:
                    h = urlparse(line).netloc
                    hosts.append(h.lower())
                except Exception:
                    pass
            # Solo considerar válido si HTTP 200 y hay al menos una URL
            if openphish_http_code == 200 and urls:
                for u in urls:
                    key = canonical_url_key(u)
                    if not key:
                        continue
                    host = key.split("/", 1)[0]
                    if _host_is_abusable(host):
                        blocklist_uris.add(_blake2b_8bytes(key.encode("utf-8")))
                        continue
                    blocklist_uris.add(_blake2b_8bytes(key.encode("utf-8")))
                for h in hosts:
                    if _host_is_abusable(h):
                        blocklist_hosts.add(_blake2b_8bytes(h.encode("utf-8")))
                        continue
                    blocklist_hosts.add(_blake2b_8bytes(h.encode("utf-8")))
                openphish_size = len(openphish_data)
                openphish_first_bytes = openphish_data[:200]
                manifest["sources"]["openphish"] = {
                    "type": "community_feed",
                    "status": "ok",
                    "http_code": openphish_http_code,
                    "response_size_bytes": openphish_size,
                    "first_bytes": openphish_first_bytes.decode("utf-8", errors="replace")
                    if openphish_first_bytes
                    else "",
                    "urls_processed": len(urls),
                    "hosts_extracted": len(set(hosts)),
                }
            else:
                # HTTP != 200 o sin URLs: tratar como omitido/no válido
                openphish_size = len(openphish_data) if openphish_data else 0
                openphish_first_bytes = openphish_data[:200] if openphish_data else b""
                manifest["sources"]["openphish"] = {
                    "type": "community_feed",
                    "status": "omitted",
                    "http_code": openphish_http_code,
                    "response_size_bytes": openphish_size,
                    "first_bytes": openphish_first_bytes.decode("utf-8", errors="replace")
                    if openphish_first_bytes
                    else "",
                    "urls_processed": len(urls),
                    "hosts_extracted": len(set(hosts)),
                    "note": f"HTTP {openphish_http_code}; feed no válido (se requiere HTTP 200 y al menos 1 URL)",
                }
        except Exception as exc:
            print(f"⚠ Error procesando OpenPhish: {exc}", file=sys.stderr)
            manifest["errors"].append("openphish error")
            manifest["sources"]["openphish"] = {
                "type": "community_feed",
                "status": "degraded",
                "error": str(exc),
            }
    else:
        print("⚠ OpenPhish feed no disponible; se registra en manifest.", file=sys.stderr)
        manifest["sources"]["openphish"] = {
            "type": "community_feed",
            "status": "omitted",
            "note": "feed no descargado",
            "urls_processed": 0,
            "hosts_extracted": 0,
        }

    # URLhaus feed (texto plano de URLs en línea)
    # Soporte opcional para clave de autenticación (variable de entorno, nunca en duro)
    urlhaus_auth_key = os.getenv("URLHAUS_AUTH_KEY", None)
    if urlhaus_auth_key:
        manifest["sources"]["urlhaus"] = {
            "type": "urlhaus_feed",
            "status": "configured",
            "note": "clave URLHAUS_AUTH_KEY configurada; descarga diferida",
        }
    else:
        manifest["sources"]["urlhaus"] = {
            "type": "urlhaus_feed",
            "status": "omitted",
            "note": "requiere API key (URLHAUS_AUTH_KEY); omitido por defecto",
        }

    # PhishTank (solo si hay app key, opcional)
    phishtank_api_key = os.getenv("PHISHTANK_API_KEY", None)
    if phishtank_api_key:
        manifest["sources"]["phishtank"] = {
            "type": "phishtank_api",
            "status": "configured",
            "note": "clave PHISHTANK_API_KEY configurada",
        }
    else:
        manifest["sources"]["phishtank"] = {
            "type": "phishtank_api",
            "status": "omitted",
            "note": "apikey opcional; omitido por defecto",
        }

    # Validar mínimos
    if len(blocklist_hosts) < 100_000:
        raise RuntimeError(f"Blocklist hosts demasiado pequeño: {len(blocklist_hosts)} (< 100000)")

    # Ordenar hashes y escribir binarios
    sorted_hashes = sorted(blocklist_uris, key=lambda b: b.hex())
    BLOCKLIST_DIR.mkdir(parents=True, exist_ok=True)
    blocklist_urls_path = BLOCKLIST_DIR / "blocklist_urls.bin"
    with blocklist_urls_path.open("wb") as f:
        for h in sorted_hashes:
            f.write(h)
    manifest["sources"]["blocklist_urls"] = {
        "type": "blake2b_8bytes",
        "count": len(sorted_hashes),
        "path": str(blocklist_urls_path.relative_to(ROOT)),
        "sha256": _sha256(blocklist_urls_path),
    }

    sorted_hosts = sorted(blocklist_hosts)
    blocklist_hosts_path = BLOCKLIST_DIR / "blocklist_hosts.bin"
    with blocklist_hosts_path.open("wb") as f:
        for h in sorted_hosts:
            f.write(h)  # h ya es bytes (hash blake2b de 8 bytes)
    manifest["sources"]["blocklist_hosts"] = {
        "type": "blake2b_8bytes",
        "count": len(sorted_hosts),
        "path": str(blocklist_hosts_path.relative_to(ROOT)),
        "sha256": _sha256(blocklist_hosts_path),
    }

    # El modelo es un artefacto de solo lectura más: su SHA-256 se declara en
    # el mismo manifiesto para que runtime lo verifique al arranque (RNF-107).
    if MODEL_PATH.is_file():
        manifest["sources"]["model_v1"] = {
            "type": "linear_model_json",
            "path": str(MODEL_PATH.relative_to(ROOT)),
            "size_bytes": MODEL_PATH.stat().st_size,
            "sha256": _sha256(MODEL_PATH),
        }
    else:
        manifest["sources"].pop("model_v1", None)

    # Calcular tamaño total de los artefactos generados
    total_bytes = 0
    for p in [
        ALLOWLIST_PATH,
        blocklist_urls_path,
        blocklist_hosts_path,
        MODEL_PATH,
        MANIFEST_PATH,
    ]:
        if p.exists():
            total_bytes += p.stat().st_size
    if total_bytes > MAX_TOTAL_BYTES:
        raise RuntimeError(
            f"Artefactos demasiado grandes: {total_bytes} bytes (> {MAX_TOTAL_BYTES})"
        )
    manifest["total_size_mb"] = total_bytes / (1024 * 1024)
    print("✔ Tamaño total de artefactos: {:.2f} MB".format(manifest["total_size_mb"]))

    # Escribir manifest
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"✔ Manifest escrito en {MANIFEST_PATH}")

    return manifest


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    manifest = build_artifacts()
    print("\n--- Resumen del manifest ---")
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
