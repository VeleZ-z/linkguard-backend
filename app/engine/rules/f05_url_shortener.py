"""F05 — Uso de acortador de URL (RF-205).

Regla pura: compara el host normalizado contra el hashset estático de
acortadores conocidos, aceptando también subdominios de un dominio listado.
"""

from __future__ import annotations

from typing import Final

from app.engine.data.url_shorteners import URL_SHORTENERS
from app.engine.models import ParsedURL, RuleResult
from app.engine.rules.base import build_rule_result
from app.engine.weights import WEIGHTS

RULE_ID: Final[str] = "F05_URL_SHORTENER"
POINTS: Final[int] = WEIGHTS["F05"]

TITLE: Final[str] = "Acortador de URL"
DESCRIPTION: Final[str] = (
    "El dominio pertenece a un servicio de acortamiento conocido, lo que "
    "oculta el destino real del enlace y dificulta su inspección."
)


def _is_shortener(host: str) -> bool:
    """Indica si ``host`` es un acortador listado o un subdominio suyo."""
    normalized = host.strip().rstrip(".").lower()
    return any(
        normalized == domain or normalized.endswith(f".{domain}") for domain in URL_SHORTENERS
    )


def evaluate_url_shortener(parsed_url: ParsedURL) -> RuleResult:
    """Activa F05 cuando el host es un acortador conocido (RF-205).

    Args:
        parsed_url: URL normalizada por el módulo de normalización.

    Returns:
        ``RuleResult`` con ``points=15`` si se activa y ``0`` si no.
    """
    activated = not parsed_url.is_ip and _is_shortener(parsed_url.host)
    return build_rule_result(
        rule_id=RULE_ID,
        points=POINTS,
        activated=activated,
        title=TITLE,
        description=DESCRIPTION,
    )


__all__ = ["DESCRIPTION", "POINTS", "RULE_ID", "TITLE", "evaluate_url_shortener"]
