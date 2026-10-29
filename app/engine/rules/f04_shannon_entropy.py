"""F04 — Entropía de Shannon del host (RF-204).

Regla pura: calcula ``H(X) = -Σ p(x)·log2 p(x)`` sobre el nombre del host y
activa cuando supera 4.5 bits por símbolo. Sin red ni estado.
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Final

from app.engine.models import ParsedURL, RuleResult
from app.engine.rules.base import build_rule_result
from app.engine.weights import WEIGHTS

RULE_ID: Final[str] = "F04_SHANNON_ENTROPY"
POINTS: Final[int] = WEIGHTS["F04"]

#: Umbral estricto de entropía que activa la regla.
MAX_ENTROPY: Final[float] = 4.5

TITLE: Final[str] = "Entropía de Shannon alta"
DESCRIPTION: Final[str] = (
    "El nombre del host presenta una aleatoriedad alta (H > 4.5), un patrón "
    "típico de dominios generados automáticamente por algoritmos DGA."
)


def shannon_entropy(value: str) -> float:
    """Calcula la entropía de Shannon de una cadena en bits por símbolo."""
    if not value:
        return 0.0
    total = len(value)
    return -sum((count / total) * math.log2(count / total) for count in Counter(value).values())


def evaluate_shannon_entropy(parsed_url: ParsedURL) -> RuleResult:
    """Activa F04 cuando la entropía del host supera 4.5 (RF-204).

    Args:
        parsed_url: URL normalizada por el módulo de normalización.

    Returns:
        ``RuleResult`` con ``points=15`` si se activa y ``0`` si no.
    """
    activated = shannon_entropy(parsed_url.host) > MAX_ENTROPY
    return build_rule_result(
        rule_id=RULE_ID,
        points=POINTS,
        activated=activated,
        title=TITLE,
        description=DESCRIPTION,
    )


__all__ = [
    "DESCRIPTION",
    "MAX_ENTROPY",
    "POINTS",
    "RULE_ID",
    "TITLE",
    "evaluate_shannon_entropy",
    "shannon_entropy",
]
