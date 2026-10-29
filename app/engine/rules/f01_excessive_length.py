"""F01 — Longitud excesiva de la URL (RF-201).

Regla pura: activa cuando la URL normalizada alcanza los 75 caracteres.
"""

from __future__ import annotations

from typing import Final

from app.engine.models import ParsedURL, RuleResult
from app.engine.rules.base import build_rule_result
from app.engine.weights import WEIGHTS

#: Identificador estable publicado en las evidencias del contrato §6.
RULE_ID: Final[str] = "F01_EXCESSIVE_LENGTH"

#: Peso ``wᵢ`` alineado con la matriz de requisitos §3.
POINTS: Final[int] = WEIGHTS["F01"]

#: Umbral mínimo de longitud normalizada que activa la regla.
MIN_LENGTH: Final[int] = 75

TITLE: Final[str] = "Longitud excesiva de la URL"
DESCRIPTION: Final[str] = (
    "La URL normalizada tiene 75 caracteres o más, lo que puede indicar "
    "relleno deliberado o parámetros de evasión."
)


def evaluate_excessive_length(parsed_url: ParsedURL) -> RuleResult:
    """Activa F01 cuando ``normalized_url`` alcanza 75 caracteres (RF-201).

    Args:
        parsed_url: URL normalizada por el módulo de normalización.

    Returns:
        ``RuleResult`` con ``points=10`` si se activa y ``0`` si no.
    """
    activated = len(parsed_url.normalized_url) >= MIN_LENGTH
    return build_rule_result(
        rule_id=RULE_ID,
        points=POINTS,
        activated=activated,
        title=TITLE,
        description=DESCRIPTION,
    )


__all__ = [
    "DESCRIPTION",
    "MIN_LENGTH",
    "POINTS",
    "RULE_ID",
    "TITLE",
    "evaluate_excessive_length",
]
