"""F06 — Símbolo ``@`` en la URL (RF-206, R-EDGE-04).

Regla pura: activa cuando ``@`` aparece en la ubicación de red (incluido
userinfo) o en el path. Soporta múltiples ``@`` encadenados.
"""

from __future__ import annotations

from typing import Final

from app.engine.models import ParsedURL, RuleResult
from app.engine.rules.base import build_rule_result
from app.engine.weights import WEIGHTS

RULE_ID: Final[str] = "F06_AT_SYMBOL"
POINTS: Final[int] = WEIGHTS["F06"]

TITLE: Final[str] = "Símbolo @ en la URL"
DESCRIPTION: Final[str] = (
    "La URL contiene el carácter @ en el host o en el path, lo que puede "
    "hacer que el navegador ignore la parte previa y se conecte a otro host."
)


def evaluate_at_symbol(parsed_url: ParsedURL) -> RuleResult:
    """Activa F06 cuando ``@`` aparece en ``netloc`` o ``path`` (RF-206).

    Args:
        parsed_url: URL normalizada por el módulo de normalización.

    Returns:
        ``RuleResult`` con ``points=20`` si se activa y ``0`` si no.
    """
    activated = "@" in parsed_url.netloc or "@" in parsed_url.path
    return build_rule_result(
        rule_id=RULE_ID,
        points=POINTS,
        activated=activated,
        title=TITLE,
        description=DESCRIPTION,
    )


__all__ = ["DESCRIPTION", "POINTS", "RULE_ID", "TITLE", "evaluate_at_symbol"]
