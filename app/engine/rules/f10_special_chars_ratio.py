"""F10 — Ratio de caracteres especiales (RF-210).

Regla pura: calcula la proporción de ``? = % - _ &`` sobre la longitud total
de la URL normalizada y activa cuando supera el 15 %.
"""

from __future__ import annotations

from typing import Final

from app.engine.models import ParsedURL, RuleResult
from app.engine.rules.base import build_rule_result
from app.engine.weights import WEIGHTS

RULE_ID: Final[str] = "F10_SPECIAL_CHARS_RATIO"
POINTS: Final[int] = WEIGHTS["F10"]

#: Caracteres cuyo exceso delata inundación de parámetros o codificaciones.
SPECIAL_CHARS: Final[frozenset[str]] = frozenset({"?", "=", "%", "-", "_", "&"})

#: Umbral estricto de proporción que activa la regla.
MAX_RATIO: Final[float] = 0.15

TITLE: Final[str] = "Ratio elevado de caracteres especiales"
DESCRIPTION: Final[str] = (
    "La URL contiene más de un 15 % de caracteres especiales, un patrón "
    "habitual en parámetros ofuscados o redirecciones encadenadas."
)


def special_chars_ratio(value: str) -> float:
    """Calcula la proporción de caracteres especiales sobre ``value``."""
    if not value:
        return 0.0
    return sum(1 for char in value if char in SPECIAL_CHARS) / len(value)


def evaluate_special_chars_ratio(parsed_url: ParsedURL) -> RuleResult:
    """Activa F10 cuando la proporción de especiales supera 0.15 (RF-210).

    Args:
        parsed_url: URL normalizada por el módulo de normalización.

    Returns:
        ``RuleResult`` con ``points=7`` si se activa y ``0`` si no.
    """
    activated = special_chars_ratio(parsed_url.normalized_url) > MAX_RATIO
    return build_rule_result(
        rule_id=RULE_ID,
        points=POINTS,
        activated=activated,
        title=TITLE,
        description=DESCRIPTION,
    )


__all__ = [
    "DESCRIPTION",
    "MAX_RATIO",
    "POINTS",
    "RULE_ID",
    "SPECIAL_CHARS",
    "TITLE",
    "evaluate_special_chars_ratio",
    "special_chars_ratio",
]
