"""F08 — Desvío de esquema en path o query (RF-208).

Regla pura: activa cuando las subcadenas ``http:`` o ``https:`` aparecen
dentro del path o de la cadena de consulta, un patrón típico para simular un
destino legítimo dentro de los parámetros de la URL.
"""

from __future__ import annotations

from typing import Final

from app.engine.models import ParsedURL, RuleResult
from app.engine.rules.base import build_rule_result
from app.engine.weights import WEIGHTS

RULE_ID: Final[str] = "F08_SCHEMA_REDIRECT"
POINTS: Final[int] = WEIGHTS["F08"]

#: Subcadenas de esquema que delatan un desvío embebido.
SCHEME_MARKERS: Final[tuple[str, ...]] = ("http:", "https:")

TITLE: Final[str] = "Desvío de esquema en la URL"
DESCRIPTION: Final[str] = (
    "La ruta o los parámetros contienen otro esquema http/https, lo que puede "
    "redirigir al usuario a un destino distinto del dominio mostrado."
)


def evaluate_schema_redirect(parsed_url: ParsedURL) -> RuleResult:
    """Activa F08 cuando ``http:`` o ``https:`` aparecen en path/query (RF-208).

    Args:
        parsed_url: URL normalizada por el módulo de normalización.

    Returns:
        ``RuleResult`` con ``points=20`` si se activa y ``0`` si no.
    """
    haystack = f"{parsed_url.path} {parsed_url.query}".lower()
    activated = any(marker in haystack for marker in SCHEME_MARKERS)
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
    "SCHEME_MARKERS",
    "TITLE",
    "evaluate_schema_redirect",
]
