"""Canonicalización de claves de URL para feeds de reputación (RF-502, RF-504).

La función :func:`canonical_url_key` produce una clave determinista a partir de
una URL: host en minúsculas, sin esquema, sin consulta, sin fragmento y sin
barra final. Se usa tanto en el generador de artefactos (build) como en el
runtime para hacer match contra blocklists/allowlists.
"""

from __future__ import annotations

from urllib.parse import urlparse


def canonical_url_key(url: str) -> str:
    """Devuelve la clave canónica de una URL para búsquedas de reputación.

    La clave normaliza: host en minúsculas, elimina esquema, consulta y
    fragmento, y quita la barra final del path. El host se extrae tal cual
    (sin conversión IDN/punycode aquí; el caller debe normalizar previamente
    si se requiere consistencia con punycode).

    Args:
        url: URL original o ya normalizada.

    Returns:
        Clave canónica de la forma ``host/path`` (sin barra final) o solo
        ``host`` cuando no hay path.
    """
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host:
        return ""
    path = parsed.path or ""
    # Quitar barra final (rstrip elimina todas las barras finales)
    path = path.rstrip("/")
    key = host + path
    return key


__all__ = ["canonical_url_key"]
