"""Infraestructura compartida de las reglas léxicas puras (RF-201…RF-211).

Define el contrato que cumplen las 11 funciones puras del motor y un
constructor común de ``RuleResult``. Ninguna regla realiza peticiones de red
(RNF-101), escribe en disco (RNF-103) ni depende de estado global: todas son
funciones deterministas sobre un ``ParsedURL`` ya normalizado.
"""

from __future__ import annotations

from typing import Protocol

from app.engine.models import ParsedURL, RuleResult


class RuleEvaluator(Protocol):
    """Contrato de una regla léxica pura del motor."""

    def __call__(self, parsed_url: ParsedURL) -> RuleResult:
        """Evalúa la regla sobre una URL ya normalizada."""
        ...


def build_rule_result(
    *,
    rule_id: str,
    points: int,
    activated: bool,
    title: str,
    description: str,
) -> RuleResult:
    """Construye un ``RuleResult``; los puntos solo cuentan si la regla se activa.

    Args:
        rule_id: Identificador estable de la regla (ej. ``F01_EXCESSIVE_LENGTH``).
        points: Peso ``wᵢ`` que aporta la regla cuando se activa.
        activated: Resultado booleano de la evaluación.
        title: Título técnico legible de la anomalía.
        description: Explicación en español neutro para el usuario final.

    Returns:
        ``RuleResult`` con ``points=0`` cuando ``activated`` es ``False``.
    """
    return RuleResult(
        rule_id=rule_id,
        activated=activated,
        points=points if activated else 0,
        title=title,
        description=description,
    )


__all__ = ["RuleEvaluator", "build_rule_result"]
