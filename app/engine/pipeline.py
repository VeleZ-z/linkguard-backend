"""Pipeline determinista de evaluación léxica (RF-301, RNF-102).

Ejecuta las 11 reglas puras sobre una URL ya normalizada, sin red ni estado
compartido. El resultado conserva el orden del registro F01…F11.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from app.engine.models import ParsedURL, RuleResult
from app.engine.rules.registry import RULES, Rule

#: Reglas ejecutadas por el pipeline, en orden numérico estable.
PIPELINE_RULES: Final[Sequence[Rule]] = RULES


def run_rules(parsed_url: ParsedURL) -> list[RuleResult]:
    """Evalúa las 11 reglas léxicas sobre una URL normalizada.

    Args:
        parsed_url: URL ya descompuesta por el normalizador sintáctico.

    Returns:
        Lista con los 11 ``RuleResult`` en orden F01…F11. Cada resultado
        incluye ``activated`` y ``points`` (``0`` si no se activó).
    """
    return [rule.evaluate(parsed_url) for rule in PIPELINE_RULES]


__all__ = ["PIPELINE_RULES", "run_rules"]
