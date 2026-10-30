"""Construcción del desglose de evidencias (RF-303, RF-405, RNF-106).

Solo las reglas activadas generan evidencia; cada elemento conserva el
``rule_id``, los puntos, el título técnico y la descripción en es-419. La
coincidencia en la lista negra de PhishTank se representa con una evidencia
adicional de 50 puntos.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Final

from app.engine.models import RuleResult
from app.schemas import EvidenceDTO
from app.scoring.scorer import PHISHTANK_POINTS, PHISHTANK_RULE_ID

#: Título y descripción literales de la evidencia de reputación (RF-405).
PHISHTANK_TITLE: Final[str] = "Reporte en lista negra de PhishTank"
PHISHTANK_DESCRIPTION: Final[str] = (
    "La URL figura en la lista negra activa de PhishTank, por lo que el "
    "análisis se eleva automáticamente a riesgo Alto."
)


def to_evidence(result: RuleResult) -> EvidenceDTO:
    """Convierte un ``RuleResult`` en el DTO de evidencia del contrato."""
    return EvidenceDTO(
        rule_id=result.rule_id,
        points=result.points,
        title=result.title,
        description=result.description,
    )


def phishtank_evidence() -> EvidenceDTO:
    """Construye la evidencia de coincidencia en PhishTank (RF-405)."""
    return EvidenceDTO(
        rule_id=PHISHTANK_RULE_ID,
        points=PHISHTANK_POINTS,
        title=PHISHTANK_TITLE,
        description=PHISHTANK_DESCRIPTION,
    )


def build_evidences(
    results: Iterable[RuleResult],
    *,
    phishtank_match: bool = False,
) -> list[EvidenceDTO]:
    """Devuelve las evidencias de las reglas activadas, en orden de entrada.

    Args:
        results: Resultados de las reglas léxicas.
        phishtank_match: Si es ``True``, se añade al final la evidencia
            ``MATCH_PHISHTANK`` con 50 puntos.

    Returns:
        Evidencias léxicas activadas y, si aplica, la de reputación externa.
    """
    evidences = [to_evidence(result) for result in results if result.activated]
    if phishtank_match:
        evidences.append(phishtank_evidence())
    return evidences


__all__ = [
    "PHISHTANK_DESCRIPTION",
    "PHISHTANK_TITLE",
    "build_evidences",
    "phishtank_evidence",
    "to_evidence",
]
