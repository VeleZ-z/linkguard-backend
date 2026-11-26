"""Cargador de artefactos de reputación (RF-505, RF-506).

Verifica los tres artefactos contra el SHA-256 declarado en ``manifest.json``
y expone señales de reputación para una URL ya parseada. Un artefacto ausente
o modificado degrada solo esa fuente: nunca se lanza una excepción ni se
responde HTTP 500. Todo opera en memoria volátil (RNF-103) y sin red
(RNF-101).
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.engine.models import ParsedURL
from app.reputation.allowlist import ALLOWLIST_PATH, is_allowlisted, load_allowlist
from app.reputation.blocklist import (
    BLOCKLIST_HOSTS_PATH,
    BLOCKLIST_URLS_PATH,
    hash_canonical,
    lookup_host,
    lookup_url,
)
from app.reputation.canonical import canonical_url_key

_log = logging.getLogger("linkguard.reputation")

#: Ruta al manifiesto con los SHA-256 esperados de los artefactos.
MANIFEST_PATH: Path = (
    Path(__file__).resolve().parents[2] / "app" / "engine" / "data" / "blocklist" / "manifest.json"
)

#: Tamaño del bloque de lectura para calcular SHA-256 sin cargar 9 MB de golpe.
_CHUNK_SIZE: int = 1024 * 1024

#: Límite máximo por artefacto (RNF-107). Los valores actuales están muy por
#: debajo del tope y dejan holgura para el refresco semanal de feeds.
MAX_ARTIFACT_BYTES: dict[str, int] = {
    "allowlist": 4 * 1024 * 1024,
    "blocklist_urls": 8 * 1024 * 1024,
    "blocklist_hosts": 6 * 1024 * 1024,
}

#: Estado por artefacto: "ok", "degraded" o "missing".
_load_status: dict[str, str] = {
    "allowlist": "missing",
    "blocklist_urls": "missing",
    "blocklist_hosts": "missing",
}

#: Evita repetir la verificación en cada solicitud.
_loaded: bool = False

#: Cerrojo para la carga concurrente (arranque + primera petición).
_load_lock: threading.Lock = threading.Lock()


class ReputationSignals:
    """Señales de reputación devueltas por :func:`get_reputation`.

    Atributos:
        allowlisted: True si el host está en la allowlist (RF-502).
        abusable: True si coincide con ``ABUSABLE_SERVICES`` (RF-503).
        feed_url: True si la clave canónica de la URL está en el blocklist (RF-504).
        feed_host: True si el host está en el blocklist (RF-504).
    """

    __slots__ = ("allowlisted", "abusable", "feed_url", "feed_host")

    def __init__(
        self,
        allowlisted: bool = False,
        abusable: bool = False,
        feed_url: bool = False,
        feed_host: bool = False,
    ) -> None:
        self.allowlisted = allowlisted
        self.abusable = abusable
        self.feed_url = feed_url
        self.feed_host = feed_host

    def __bool__(self) -> bool:
        """True si alguna señal está activa."""
        return self.allowlisted or self.abusable or self.feed_url or self.feed_host

    def __repr__(self) -> str:
        """Representación legible para diagnóstico."""
        return (
            f"ReputationSignals(allowlisted={self.allowlisted}, "
            f"abusable={self.abusable}, feed_url={self.feed_url}, "
            f"feed_host={self.feed_host})"
        )


def _sha256_of(path: Path) -> str | None:
    """Calcula el SHA-256 hexadecimal de *path*, o None si no es legible."""
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while True:
                bloque = handle.read(_CHUNK_SIZE)
                if not bloque:
                    break
                digest.update(bloque)
    except OSError as exc:
        _log.warning(
            "REPUTATION_ARTIFACT_INVALID: no se pudo leer %s (%s)",
            path.name,
            type(exc).__name__,
        )
        return None
    return digest.hexdigest()


def _manifest_sha256(key: str) -> str | None:
    """Obtiene el SHA-256 esperado de *key* desde ``manifest.json``."""
    try:
        contenido: Any = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        esperado: Any = contenido.get("sources", {}).get(key, {}).get("sha256")
    except Exception as exc:
        _log.warning(
            "REPUTATION_ARTIFACT_INVALID: manifiesto no legible para %s (%s)",
            key,
            type(exc).__name__,
        )
        return None
    return esperado if isinstance(esperado, str) and esperado else None


def _registrar_mismatch(nombre: str, actual: str | None, esperado: str) -> None:
    """Marca un artefacto como degradado y registra los prefijos de ambos hashes."""
    _load_status[nombre] = "degraded"
    _log.warning(
        "REPUTATION_ARTIFACT_INVALID: %s SHA mismatch (actual=%s expected=%s)",
        nombre,
        (actual or "")[:8],
        esperado[:8],
    )


def _verify_and_load_allowlist() -> None:
    """Verifica el SHA-256 de la allowlist y la carga si es íntegra."""
    if not ALLOWLIST_PATH.is_file():
        _load_status["allowlist"] = "missing"
        _log.warning(
            "REPUTATION_ARTIFACT_INVALID: allowlist no encontrado en %s",
            ALLOWLIST_PATH,
        )
        return

    if ALLOWLIST_PATH.stat().st_size > MAX_ARTIFACT_BYTES["allowlist"]:
        _load_status["allowlist"] = "degraded"
        _log.warning("REPUTATION_ARTIFACT_INVALID: allowlist excede el tamaño máximo")
        return

    actual = _sha256_of(ALLOWLIST_PATH)
    esperado = _manifest_sha256("allowlist")
    if actual is None or esperado is None:
        _load_status["allowlist"] = "degraded"
        _log.warning("REPUTATION_ARTIFACT_INVALID: allowlist sin SHA-256 verificable")
        return
    if actual != esperado:
        _registrar_mismatch("allowlist", actual, esperado)
        return

    try:
        count = load_allowlist()
    except Exception as exc:
        _load_status["allowlist"] = "degraded"
        _log.warning(
            "REPUTATION_ARTIFACT_INVALID: allowlist no cargable (%s)",
            type(exc).__name__,
        )
        return

    _load_status["allowlist"] = "ok" if count > 0 else "degraded"


def _verify_and_load_blocklist(key: str, path: Path, artifact_name: str) -> None:
    """Verifica el SHA-256 de un blocklist y actualiza su estado.

    La búsqueda real carga el binario de forma perezosa en ``blocklist.py``;
    aquí solo se comprueba la integridad contra el manifiesto.
    """
    if not path.is_file():
        _load_status[artifact_name] = "missing"
        _log.warning("REPUTATION_ARTIFACT_INVALID: %s no encontrado", artifact_name)
        return

    if path.stat().st_size > MAX_ARTIFACT_BYTES[artifact_name]:
        _load_status[artifact_name] = "degraded"
        _log.warning("REPUTATION_ARTIFACT_INVALID: %s excede el tamaño máximo", artifact_name)
        return

    actual = _sha256_of(path)
    esperado = _manifest_sha256(key)
    if actual is None or esperado is None:
        _load_status[artifact_name] = "degraded"
        _log.warning(
            "REPUTATION_ARTIFACT_INVALID: %s sin SHA-256 verificable",
            artifact_name,
        )
        return
    if actual != esperado:
        _registrar_mismatch(artifact_name, actual, esperado)
        return

    _load_status[artifact_name] = "ok"


def _ensure_loaded() -> None:
    """Verifica los tres artefactos una sola vez (operación idempotente).

    El cerrojo evita que la carga disparada al arranque y la primera petición
    concurrentes dupliquen la verificación (RNF-107/RNF-109).
    """
    global _loaded

    with _load_lock:
        if _loaded:
            return

        verificaciones: tuple[tuple[str, Callable[..., None], tuple[Any, ...]], ...] = (
            ("allowlist", _verify_and_load_allowlist, ()),
            (
                "blocklist_urls",
                _verify_and_load_blocklist,
                ("blocklist_urls", BLOCKLIST_URLS_PATH, "blocklist_urls"),
            ),
            (
                "blocklist_hosts",
                _verify_and_load_blocklist,
                ("blocklist_hosts", BLOCKLIST_HOSTS_PATH, "blocklist_hosts"),
            ),
        )

        for nombre, funcion, argumentos in verificaciones:
            try:
                funcion(*argumentos)
            except Exception as exc:
                _load_status[nombre] = "degraded"
                _log.warning(
                    "REPUTATION_ARTIFACT_INVALID: fallo al verificar %s (%s)",
                    nombre,
                    type(exc).__name__,
                )

        _loaded = True


def get_load_status() -> dict[str, str]:
    """Devuelve el estado real de carga de cada artefacto de reputación.

    Returns:
        Copia de un diccionario con claves ``allowlist``, ``blocklist_urls``
        y ``blocklist_hosts``. Valores: "ok", "degraded" o "missing".
    """
    _ensure_loaded()
    return _load_status.copy()


def get_reputation(parsed_url: ParsedURL) -> ReputationSignals:
    """Devuelve las señales de reputación de una URL ya normalizada.

    Se acepta cualquier objeto con ``host`` y, opcionalmente,
    ``normalized_url``. Cada fuente se evalúa de forma independiente y los
    fallos locales se degradan a False sin propagar excepciones.
    """
    _ensure_loaded()

    host = str(getattr(parsed_url, "host", "") or "").lower().rstrip(".")
    normalized_url = str(getattr(parsed_url, "normalized_url", "") or "")
    señales = ReputationSignals()

    # 1. Allowlist (RF-502): precedencia sobre el resto de señales (D2).
    if _load_status["allowlist"] == "ok" and host:
        try:
            señales.allowlisted = is_allowlisted(host)
        except Exception as exc:
            _log.warning(
                "REPUTATION_ARTIFACT_INVALID: fallo en allowlist (%s)",
                type(exc).__name__,
            )

    # 2. Servicios abusables (RF-503): se incluye la ruta para patrones host+ruta.
    try:
        from app.engine.data.abusable_services import _matches_abusable

        valor = canonical_url_key(normalized_url) if normalized_url else host
        señales.abusable = _matches_abusable(valor) or _matches_abusable(host)
    except Exception as exc:
        señales.abusable = False
        _log.debug("Fallo en la evaluación de servicios abusables (%s)", type(exc).__name__)

    # 3. Blocklist de URL (RF-504): búsqueda binaria sobre la clave canónica.
    if _load_status["blocklist_urls"] == "ok" and normalized_url:
        try:
            señales.feed_url = lookup_url(normalized_url)
        except Exception as exc:
            _log.warning(
                "REPUTATION_ARTIFACT_INVALID: fallo en blocklist_urls (%s)",
                type(exc).__name__,
            )

    # 4. Blocklist de host (RF-504): búsqueda binaria sobre el host.
    if _load_status["blocklist_hosts"] == "ok" and host:
        try:
            señales.feed_host = lookup_host(host)
        except Exception as exc:
            _log.warning(
                "REPUTATION_ARTIFACT_INVALID: fallo en blocklist_hosts (%s)",
                type(exc).__name__,
            )

    return señales


__all__ = [
    "get_reputation",
    "ReputationSignals",
    "get_load_status",
    "BLOCKLIST_URLS_PATH",
    "BLOCKLIST_HOSTS_PATH",
    "ALLOWLIST_PATH",
    "is_allowlisted",
    "hash_canonical",
    "lookup_url",
    "lookup_host",
]
