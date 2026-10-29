"""F03 — Subdominios múltiples (RF-203).

Regla pura: cuenta los niveles de subdominio con la *Public Suffix List*
(``publicsuffix2``) y activa cuando hay tres o más. No realiza red.
"""

from __future__ import annotations

from typing import Final

from publicsuffix2 import get_sld

from app.engine.models import ParsedURL, RuleResult
from app.engine.rules.base import build_rule_result
from app.engine.weights import WEIGHTS

RULE_ID: Final[str] = "F03_MULTIPLE_SUBDOMAINS"
POINTS: Final[int] = WEIGHTS["F03"]

#: Número mínimo de etiquetas de subdominio que activa la regla.
MIN_SUBDOMAINS: Final[int] = 3

TITLE: Final[str] = "Múltiples subdominios"
DESCRIPTION: Final[str] = (
    "La URL usa tres o más niveles de subdominio, un patrón habitual para "
    "incrustar nombres de marcas legítimas en dominios de terceros."
)


def _count_subdomains(host: str) -> int:
    """Cuenta las etiquetas previas al dominio registrable (eTLD+1)."""
    normalized = host.strip().rstrip(".").lower()
    if not normalized:
        return 0
    try:
        main_domain = get_sld(normalized) or normalized
    except (TypeError, ValueError):
        main_domain = normalized
    if normalized == main_domain:
        return 0
    return max(0, len(normalized.split(".")) - len(main_domain.split(".")))


def evaluate_multiple_subdomains(parsed_url: ParsedURL) -> RuleResult:
    """Activa F03 cuando hay tres o más subdominios (RF-203).

    Args:
        parsed_url: URL normalizada por el módulo de normalización.

    Returns:
        ``RuleResult`` con ``points=10`` si se activa y ``0`` si no.
    """
    activated = not parsed_url.is_ip and _count_subdomains(parsed_url.host) >= MIN_SUBDOMAINS
    return build_rule_result(
        rule_id=RULE_ID,
        points=POINTS,
        activated=activated,
        title=TITLE,
        description=DESCRIPTION,
    )


__all__ = [
    "DESCRIPTION",
    "MIN_SUBDOMAINS",
    "POINTS",
    "RULE_ID",
    "TITLE",
    "evaluate_multiple_subdomains",
]
