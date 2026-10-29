"""F07 — Guiones en el nombre del dominio principal (RF-207).

Regla pura: cuenta los guiones del dominio registrable (eTLD+1) y activa con
dos o más. No inspecciona subdominios ni realiza red.
"""

from __future__ import annotations

from typing import Final

from app.engine.models import ParsedURL, RuleResult
from app.engine.rules.base import build_rule_result
from app.engine.weights import WEIGHTS

RULE_ID: Final[str] = "F07_HYPHENS_IN_DOMAIN"
POINTS: Final[int] = WEIGHTS["F07"]

#: Número mínimo de guiones en el dominio principal que activa la regla.
MIN_HYPHENS: Final[int] = 2

TITLE: Final[str] = "Guiones en el dominio"
DESCRIPTION: Final[str] = (
    "El dominio principal contiene dos o más guiones, una técnica habitual "
    "de typosquatting o combo-squatting que imita marcas legítimas."
)


def evaluate_hyphens_in_domain(parsed_url: ParsedURL) -> RuleResult:
    """Activa F07 cuando el dominio principal tiene 2+ guiones (RF-207).

    Args:
        parsed_url: URL normalizada por el módulo de normalización.

    Returns:
        ``RuleResult`` con ``points=8`` si se activa y ``0`` si no.
    """
    domain = (parsed_url.main_domain or parsed_url.host).strip().rstrip(".").lower()
    activated = not parsed_url.is_ip and domain.count("-") >= MIN_HYPHENS
    return build_rule_result(
        rule_id=RULE_ID,
        points=POINTS,
        activated=activated,
        title=TITLE,
        description=DESCRIPTION,
    )


__all__ = [
    "DESCRIPTION",
    "MIN_HYPHENS",
    "POINTS",
    "RULE_ID",
    "TITLE",
    "evaluate_hyphens_in_domain",
]
