"""Normalizador sintáctico de URLs (Módulo 100: RF-101 a RF-105).

La función :func:`normalize` es pura y determinista: no realiza ninguna
petición de red ni consulta servicios externos (RNF-101). Su salida es un
:class:`~app.engine.models.ParsedURL` con los seis componentes sintácticos,
el host desglosado y la URL normalizada.
"""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import unquote, urlparse, urlunparse

from publicsuffix2 import get_sld

from app.core.errors import InvalidURLError, URLTooLongError
from app.engine.models import ParsedURL

#: Longitud máxima procesable de una URL, medida tras la sanitización (RF-105).
MAX_URL_LENGTH: int = 4096

#: Esquemas aceptados por el servicio; el resto se considera entrada inválida.
ALLOWED_SCHEMES: frozenset[str] = frozenset({"http", "https"})

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_EXPLICIT_SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)
_HOSTNAME = re.compile(r"^[a-z0-9._-]+$")


def _sanitize(raw: str) -> str:
    """Aplica stripping y elimina caracteres de control invisibles (RF-101)."""
    if not isinstance(raw, str):  # pragma: no cover - defensa de tipo en runtime
        raise InvalidURLError()
    return _CONTROL_CHARS.sub("", raw).strip()


def _decode_component(value: str) -> str:
    """Decodifica los escapes ``%XX`` y descarta controles reintroducidos (RF-104)."""
    return _CONTROL_CHARS.sub("", unquote(value))


def _to_punycode(host: str) -> str:
    """Convierte un nombre de host IDN a su forma ASCII Punycode (RF-104)."""
    try:
        return host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise InvalidURLError() from exc


def _classify_host(host: str) -> tuple[bool, str]:
    """Determina si el host es una IP literal y devuelve su etiqueta canónica."""
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False, host
    return True, str(address)


def _split_domains(host: str, main_domain: str) -> list[str]:
    """Devuelve las etiquetas de subdominio previas al dominio principal."""
    if host == main_domain:
        return []
    return host.split(".")[: -len(main_domain.split("."))]


def _build_netloc(userinfo: str, host: str, port: int | None, is_ipv6: bool) -> str:
    """Reconstruye la ubicación de red preservando userinfo y corchetes IPv6."""
    host_repr = f"[{host}]" if is_ipv6 else host
    if port is not None:
        host_repr = f"{host_repr}:{port}"
    return f"{userinfo}{host_repr}"


def normalize(raw: str) -> ParsedURL:
    """Normaliza y descompone sintácticamente una URL ingresada por el usuario.

    Args:
        raw: Cadena original recibida desde el cliente.

    Returns:
        ``ParsedURL`` con los seis componentes de ``urllib.parse``, el host
        desglosado (dominio principal, subdominios, indicador de IP) y la URL
        normalizada.

    Raises:
        InvalidURLError: Si la entrada está vacía, contiene espacios o no puede
            interpretarse como un enlace HTTP/HTTPS válido.
        URLTooLongError: Si la entrada sanitizada supera los 4096 caracteres.
    """
    sanitized = _sanitize(raw)
    if not sanitized:
        raise InvalidURLError()
    if len(sanitized) > MAX_URL_LENGTH:
        raise URLTooLongError()

    candidate = sanitized if _EXPLICIT_SCHEME.match(sanitized) else f"http://{sanitized}"
    parsed = urlparse(candidate)
    scheme = parsed.scheme.lower()

    if scheme not in ALLOWED_SCHEMES:
        raise InvalidURLError()

    hostname = parsed.hostname or ""
    if not hostname or any(char.isspace() for char in parsed.netloc):
        raise InvalidURLError()

    try:
        port = parsed.port
    except ValueError as exc:
        raise InvalidURLError() from exc

    hostname = hostname.rstrip(".").lower()
    if not hostname:
        raise InvalidURLError()

    is_ip, host = _classify_host(hostname)
    if not is_ip:
        host = _to_punycode(host)
        if not _HOSTNAME.match(host) or ".." in host:
            raise InvalidURLError()

    path = _decode_component(parsed.path)
    params = _decode_component(parsed.params)
    query = _decode_component(parsed.query)
    fragment = _decode_component(parsed.fragment)

    userinfo = ""
    if "@" in parsed.netloc:
        userinfo = f"{parsed.netloc.rsplit('@', 1)[0]}@"
    is_ipv6 = is_ip and ":" in host
    netloc = _build_netloc(userinfo, host, port, is_ipv6)

    main_domain: str | None = None
    subdomains: list[str] = []
    if not is_ip:
        main_domain = get_sld(host) or host
        subdomains = _split_domains(host, main_domain)

    normalized_url = urlunparse((scheme, netloc, path, params, query, fragment))

    return ParsedURL(
        scheme=scheme,
        netloc=netloc,
        host=host,
        port=port,
        path=path,
        params=params,
        query=query,
        fragment=fragment,
        normalized_url=normalized_url,
        main_domain=main_domain,
        subdomains=subdomains,
        is_ip=is_ip,
    )


__all__ = ["ALLOWED_SCHEMES", "MAX_URL_LENGTH", "normalize"]
