"""F09 — Puerto no estándar (RF-209).

Regla pura: activa cuando la ubicación de red declara un puerto explícito
distinto de 80 (HTTP) y 443 (HTTPS), un indicio de canalización para evadir
filtros web estándar.
"""

from __future__ import annotations

from typing import Final

from app.engine.models import ParsedURL, RuleResult
from app.engine.rules.base import build_rule_result
from app.engine.weights import WEIGHTS

RULE_ID: Final[str] = "F09_NON_STANDARD_PORT"
POINTS: Final[int] = WEIGHTS["F09"]

#: Puertos considerados estándar para tráfico web.
STANDARD_PORTS: Final[frozenset[int]] = frozenset({80, 443})

TITLE: Final[str] = "Puerto no estándar"
DESCRIPTION: Final[str] = (
    "La URL especifica un puerto distinto de 80 o 443, lo que puede indicar "
    "tráfico canalizado para evadir filtros web habituales."
)


def evaluate_non_standard_port(parsed_url: ParsedURL) -> RuleResult:
    """Activa F09 cuando hay un puerto explícito fuera de {80, 443} (RF-209).

    Args:
        parsed_url: URL normalizada por el módulo de normalización.

    Returns:
        ``RuleResult`` con ``points=10`` si se activa y ``0`` si no.
    """
    activated = parsed_url.port is not None and parsed_url.port not in STANDARD_PORTS
    return build_rule_result(
        rule_id=RULE_ID,
        points=POINTS,
        activated=activated,
        title=TITLE,
        description=DESCRIPTION,
    )


__all__ = [
    "DESCRIPTION",
    "POINTS",
    "RULE_ID",
    "STANDARD_PORTS",
    "TITLE",
    "evaluate_non_standard_port",
]
