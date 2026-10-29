"""Construcción del desglose de evidencias (RF-303, RNF-106).

Solo las reglas activadas generan evidencia; cada elemento conserva el
``rule_id``, los puntos, el título técnico y la descripción en es-419.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.engine.models import RuleResult
from app.schemas import EvidenceDTO


def to_evidence(result: RuleResult) -> EvidenceDTO:
    """Convierte un ``RuleResult`` en el DTO de evidencia del contrato."""
    return EvidenceDTO(
        rule_id=result.rule_id,
        points=result.points,
        title=result.title,
        description=result.description,
    )


def build_evidences(results: Iterable[RuleResult]) -> list[EvidenceDTO]:
    """Devuelve las evidencias de las reglas activadas, en orden de entrada."""
    return [to_evidence(result) for result in results if result.activated]


__all__ = ["build_evidences", "to_evidence"]
