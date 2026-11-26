"""Blocklist local de hashes blake2b-8 (RF-504).

Los binarios contienen hashes de 8 bytes ordenados; las búsquedas usan
``bisect`` sobre un ``array('Q')`` cargado una sola vez en memoria. Todo el
proceso es local: sin red (RNF-101) y sin escrituras en disco (RNF-103).
"""

from __future__ import annotations

import bisect
import hashlib
import sys
from array import array
from collections.abc import Sequence
from pathlib import Path

from app.reputation.canonical import canonical_url_key

#: Ruta base de los datos de reputación (artefactos de solo lectura).
DATA_DIR: Path = Path(__file__).resolve().parents[2] / "app" / "engine" / "data"

#: Ruta al blocklist de claves canónicas de URL.
BLOCKLIST_URLS_PATH: Path = DATA_DIR / "blocklist" / "blocklist_urls.bin"

#: Ruta al blocklist de hosts normalizados.
BLOCKLIST_HOSTS_PATH: Path = DATA_DIR / "blocklist" / "blocklist_hosts.bin"

#: Cachés de módulo: se llenan con la primera consulta a cada artefacto.
_URL_HASHES: array | None = None
_HOST_HASHES: array | None = None


def hash_canonical(texto: str) -> int:
    """Devuelve el hash blake2b de 8 bytes de *texto* interpretado big-endian.

    Es la misma transformación usada al generar los binarios (RF-504). No se
    emplea la función ``hash()`` de Python, cuyo resultado no es estable.
    """
    digest = hashlib.blake2b(texto.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big")


def _load_hashes(path: Path) -> array:
    """Carga un binario de hashes ordenados en un ``array('Q')``.

    Los archivos se generan con hashes big-endian; en plataformas
    little-endian se invierte el orden de bytes de cada elemento para que las
    comparaciones numéricas con :func:`hash_canonical` sean correctas. Un
    archivo ausente o inválido produce un arreglo vacío, sin excepciones.
    """
    hashes = array("Q")
    try:
        datos = path.read_bytes()
    except OSError:
        return hashes

    if len(datos) < 8 or len(datos) % 8 != 0:
        return hashes

    hashes.frombytes(datos)
    if sys.byteorder == "little":
        hashes.byteswap()
    return hashes


def _contains(hashes: Sequence[int], valor: int) -> bool:
    """Busca *valor* en la secuencia ordenada de hashes con búsqueda binaria."""
    indice = bisect.bisect_left(hashes, valor)
    return indice < len(hashes) and hashes[indice] == valor


def lookup_url(url_normalized: str) -> bool:
    """Indica si la clave canónica de *url_normalized* está en el blocklist.

    La URL se reduce con :func:`canonical_url_key` antes de aplicar el hash,
    igual que en la generación del artefacto. Si se recibe directamente una
    clave canónica (sin esquema), se usa tal cual.
    """
    global _URL_HASHES

    texto = url_normalized.strip()
    if not texto:
        return False

    if "://" in texto or texto.startswith("//"):
        clave = canonical_url_key(texto)
    else:
        clave = texto.rstrip("/")
    if not clave:
        return False

    if _URL_HASHES is None:
        _URL_HASHES = _load_hashes(BLOCKLIST_URLS_PATH)
    return _contains(_URL_HASHES, hash_canonical(clave))


def lookup_host(host_normalized: str) -> bool:
    """Indica si el host normalizado está en el blocklist de hosts."""
    global _HOST_HASHES

    host = host_normalized.lower().rstrip(".")
    if not host:
        return False

    if _HOST_HASHES is None:
        _HOST_HASHES = _load_hashes(BLOCKLIST_HOSTS_PATH)
    return _contains(_HOST_HASHES, hash_canonical(host))


__all__ = [
    "BLOCKLIST_URLS_PATH",
    "BLOCKLIST_HOSTS_PATH",
    "hash_canonical",
    "lookup_url",
    "lookup_host",
]
