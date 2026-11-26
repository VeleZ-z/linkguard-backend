"""Canonicalización de claves de URL para feeds de reputación (RF-502, RF-504).

La función :func:`canonical_url_key` produce una clave determinista a partir de
una URL: host en minúsculas (con puerto si no es el por defecto), sin esquema,
sin consulta, sin fragmento y sin barra final. Se usa tanto en el generador de
artefactos (build) como en el runtime para hacer match contra blocklists/allowlists.
"""

from __future__ import annotations

from urllib.parse import urlparse


def canonical_url_key(url: str) -> str:
    """Devuelve la clave canónica de una URL para búsquedas de reputación.

    La clave normaliza: host en minúsculas (con puerto si no es el por
    defecto 80/443), elimina esquema, consulta y fragmento, y quita la
    barra final del path. La forma es ``host[:puerto]/path`` o solo ``host``
    cuando no hay path.

    Ejemplos:
        ``http://Ejemplo.COM/path``       → ``ejemplo.com/path``
        ``http://Ejemplo.COM:8080/path``  → ``ejemplo.com:8080/path``
        ``http://Ejemplo.COM/``           → ``ejemplo.com``
    """
    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        return ""
    # Normalizar host: minúsculas, quitar punto final
    host = host.lower().rstrip(".")
    # Incluir puerto si está presente y no es el por defecto
    port = parsed.port
    if port and port not in (80, 443):
        host += f":{port}"
    # Normalizar path: quitar barra final; quitar barra inicial de urlparse
    path = parsed.path or ""
    path = path.rstrip("/")
    if path.startswith("/"):
        path = path[1:]
    # Construir clave: host + (opcional) /path
    if path:
        return f"{host}/{path}"
    return host


__all__ = ["canonical_url_key"]
