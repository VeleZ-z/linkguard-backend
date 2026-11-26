"""Almacén en memoria de artefactos de reputación (RF-502, RF-504).

Carga los artefactos generados por ``scripts/ml/build_reputation_artifacts.py``
(blocklist de URLs y hosts, allowlist) y ofrece funciones de lookup usando
:func:`canonical_url_key`. Todo opera en memoria volátil (RNF-103) sin red
(RNF-101).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from app.reputation.canonical import canonical_url_key

#: Ruta base de los datos de reputación.
DATA_DIR: Path = Path(__file__).resolve().parents[2] / "app" / "engine" / "data"

#: Ruta al archivo de allowlist.
ALLOWLIST_PATH: Path = DATA_DIR / "allowlist_top100k.txt"

#: Ruta al blocklist de URLs (hashes blake2b 8 bytes, ordenados).
BLOCKLIST_URLS_PATH: Path = DATA_DIR / "blocklist" / "blocklist_urls.bin"

#: Ruta al blocklist de hosts (hashes blake2b 8 bytes, ordenados).
BLOCKLIST_HOSTS_PATH: Path = DATA_DIR / "blocklist" / "blocklist_hosts.bin"


class ReputationStore:
    """Almacén en memoria de allowlist y blocklist de reputación.

    Los blocklist se cargan como conjuntos de hashes blake2b (8 bytes) para
    permitir búsquedas O(1) por clave canónica. La allowlist se carga como
    conjunto de hosts normalizados.
    """

    def __init__(self) -> None:
        self._allowlist_hosts: set[str] = set()
        self._blocklist_url_hashes: set[bytes] = set()
        self._blocklist_host_hashes: set[bytes] = set()
        self._loaded: bool = False

    def load(self) -> None:
        """Carga los artefactos desde disco en memoria volátil.

        Si algún archivo falta, el almacén queda parcialmente cargado sin
        lanzar excepción (arranque degradado, sin HTTP 500).
        """
        # Cargar allowlist
        try:
            with ALLOWLIST_PATH.open("r", encoding="utf-8") as f:
                self._allowlist_hosts = {line.strip().lower() for line in f if line.strip()}
        except FileNotFoundError:
            self._allowlist_hosts = set()

        # Cargar blocklist de URLs
        try:
            with BLOCKLIST_URLS_PATH.open("rb") as f:
                while True:
                    chunk = f.read(8)
                    if not chunk:
                        break
                    self._blocklist_url_hashes.add(chunk)
        except FileNotFoundError:
            self._blocklist_url_hashes = set()

        # Cargar blocklist de hosts
        try:
            with BLOCKLIST_HOSTS_PATH.open("rb") as f:
                while True:
                    chunk = f.read(8)
                    if not chunk:
                        break
                    self._blocklist_host_hashes.add(chunk)
        except FileNotFoundError:
            self._blocklist_host_hashes = set()

        self._loaded = True

    def is_allowed(self, url: str) -> bool:
        """Devuelve True si la URL está en la allowlist (por host)."""
        key = canonical_url_key(url)
        host = key.split("/", 1)[0] if key else ""
        return host in self._allowlist_hosts

    def is_blocked_url(self, url: str) -> bool:
        """Devuelve True si la URL (clave canónica) está en el blocklist de URLs."""
        key = canonical_url_key(url)
        if not key:
            return False
        digest = hashlib.blake2b(key.encode("utf-8"), digest_size=8).digest()
        return digest in self._blocklist_url_hashes

    def is_blocked_host(self, host: str) -> bool:
        """Devuelve True si el host está en el blocklist de hosts."""
        host = host.lower()
        digest = hashlib.blake2b(host.encode("utf-8"), digest_size=8).digest()
        return digest in self._blocklist_host_hashes

    @property
    def loaded(self) -> bool:
        """Indica si el almacén ha sido cargado."""
        return self._loaded

    @property
    def allowlist_size(self) -> int:
        """Número de hosts en la allowlist."""
        return len(self._allowlist_hosts)

    @property
    def blocklist_urls_size(self) -> int:
        """Número de hashes de URL en el blocklist."""
        return len(self._blocklist_url_hashes)

    @property
    def blocklist_hosts_size(self) -> int:
        """Número de hashes de host en el blocklist."""
        return len(self._blocklist_host_hashes)


#: Instancia singleton del almacén de reputación.
store: ReputationStore = ReputationStore()

__all__ = [
    "ReputationStore",
    "store",
    "DATA_DIR",
    "ALLOWLIST_PATH",
    "BLOCKLIST_URLS_PATH",
    "BLOCKLIST_HOSTS_PATH",
]
