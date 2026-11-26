"""Allowlist de dominios registrables (RF-502).

Carga única en memoria desde ``app/engine/data/allowlist_top100k.txt``.
La comparación usa el dominio registrable del host normalizado. No persiste
en disco (RNF-103). La allowlist tiene precedencia sobre las señales léxicas
y los feeds de reputación (D2, RF-502).

Expone ``load_allowlist()`` (conteo de dominios cargados, con caché) y
``is_allowlisted(host_normalized)`` para las consultas.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.normalization.psl import registrable_domain

#: Ruta base de los datos de reputación (artefactos de solo lectura).
DATA_DIR: Path = Path(__file__).resolve().parents[2] / "app" / "engine" / "data"

#: Ruta al archivo de allowlist incluido en la imagen.
ALLOWLIST_PATH: Path = DATA_DIR / "allowlist_top100k.txt"

_log = logging.getLogger("linkguard.reputation")

#: Caché de módulo: se llena una sola vez con la primera consulta.
_allowlist: frozenset[str] | None = None
_allowlist_count: int = 0


def load_allowlist() -> int:
    """Carga la allowlist una única vez y devuelve el número de dominios.

    Las llamadas posteriores devuelven el conteo cacheado sin volver a leer
    el archivo. Si el artefacto no está disponible, registra el evento
    ``REPUTATION_ARTIFACT_INVALID`` y devuelve 0 sin lanzar excepciones.

    Returns:
        Número de dominios registrables cargados (0 si el archivo falta).
    """
    global _allowlist, _allowlist_count

    if _allowlist is not None:
        return _allowlist_count

    try:
        with ALLOWLIST_PATH.open("r", encoding="utf-8") as handle:
            dominios = {linea.strip().lower().rstrip(".") for linea in handle if linea.strip()}
    except OSError:
        _log.warning(
            "REPUTATION_ARTIFACT_INVALID: allowlist no encontrado en %s",
            ALLOWLIST_PATH,
        )
        return 0

    _allowlist = frozenset(dominios)
    _allowlist_count = len(_allowlist)
    return _allowlist_count


def is_allowlisted(host_normalized: str) -> bool:
    """Indica si el host normalizado pertenece a la allowlist.

    El host se normaliza a minúsculas y sin punto final, y se reduce a su
    dominio registrable mediante la PSL vendorizada antes de compararlo con
    el conjunto cacheado. Si aún no hay caché, se carga de forma perezosa.
    """
    global _allowlist

    if _allowlist is None:
        load_allowlist()
    if _allowlist is None:
        return False

    host = host_normalized.lower().rstrip(".")
    if not host:
        return False

    dominio = registrable_domain(host).lower().rstrip(".")
    return dominio in _allowlist


__all__ = ["is_allowlisted", "ALLOWLIST_PATH", "load_allowlist"]
