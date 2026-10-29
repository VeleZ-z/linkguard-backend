"""F02 — Dirección IP directa en el host (RF-202, R-EDGE-03).

Regla pura: activa cuando el host es una IP literal IPv4 (decimal, octal o
hexadecimal) o IPv6. No resuelve DNS ni abre conexiones (RNF-101).
"""

from __future__ import annotations

import ipaddress
from typing import Final

from app.engine.models import ParsedURL, RuleResult
from app.engine.rules.base import build_rule_result
from app.engine.weights import WEIGHTS

RULE_ID: Final[str] = "F02_DIRECT_IP"
POINTS: Final[int] = WEIGHTS["F02"]

TITLE: Final[str] = "Dirección IP directa"
DESCRIPTION: Final[str] = (
    "El host es una dirección IP literal en lugar de un nombre de dominio, "
    "lo que impide verificar la identidad del sitio mediante DNS."
)

_IPV4_OCTETS: Final[int] = 4
_MAX_OCTET: Final[int] = 255
_DECIMAL_BASE: Final[int] = 10
_OCTAL_BASE: Final[int] = 8
_HEX_BASE: Final[int] = 16


def _parse_ipv4_octet(octet: str) -> int | None:
    """Convierte un octeto decimal, octal (``0…``) o hexadecimal (``0x…``)."""
    if not octet:
        return None
    if octet.lower().startswith("0x"):
        base, digits = _HEX_BASE, octet[2:]
    elif len(octet) > 1 and octet.startswith("0"):
        base, digits = _OCTAL_BASE, octet[1:]
    else:
        base, digits = _DECIMAL_BASE, octet
    if not digits:
        return None
    try:
        return int(digits, base)
    except ValueError:
        return None


def _is_ipv4(host: str) -> bool:
    """Detecta IPv4 en notación decimal, octal o hexadecimal."""
    octets = host.split(".")
    if len(octets) != _IPV4_OCTETS:
        return False
    values = [_parse_ipv4_octet(octet) for octet in octets]
    return all(value is not None and 0 <= value <= _MAX_OCTET for value in values)


def _is_ip_literal(host: str) -> bool:
    """Determina si ``host`` es una IP literal IPv4 o IPv6 soportada."""
    candidate = host.strip().strip("[]")
    if not candidate:
        return False
    try:
        ipaddress.ip_address(candidate)
    except ValueError:
        return _is_ipv4(candidate)
    return True


def evaluate_direct_ip(parsed_url: ParsedURL) -> RuleResult:
    """Activa F02 cuando el host es una IP literal (RF-202).

    Args:
        parsed_url: URL normalizada por el módulo de normalización.

    Returns:
        ``RuleResult`` con ``points=25`` si se activa y ``0`` si no.
    """
    activated = parsed_url.is_ip or _is_ip_literal(parsed_url.host)
    return build_rule_result(
        rule_id=RULE_ID,
        points=POINTS,
        activated=activated,
        title=TITLE,
        description=DESCRIPTION,
    )


__all__ = ["DESCRIPTION", "POINTS", "RULE_ID", "TITLE", "evaluate_direct_ip"]
