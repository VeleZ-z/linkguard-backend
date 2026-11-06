"""Construcción del desglose de evidencias (RF-303, RF-405, RNF-106).

Solo las reglas activadas generan evidencia; cada elemento conserva el
``rule_id``, los puntos, el título técnico y la descripción en es-419. La
reputación externa aporta dos evidencias mutuamente excluyentes: coincidencia
confirmada en la lista negra (50 puntos) o reporte pendiente de verificación
(15 puntos).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Final

from app.engine.models import RuleResult
from app.schemas import EvidenceDTO
from app.scoring.scorer import (
    PHISHTANK_POINTS,
    PHISHTANK_RULE_ID,
    PHISHTANK_UNVERIFIED_POINTS,
    PHISHTANK_UNVERIFIED_RULE_ID,
)

#: Título y descripción literales de la evidencia de reputación (RF-405).
PHISHTANK_TITLE: Final[str] = "Reporte en lista negra de PhishTank"
PHISHTANK_DESCRIPTION: Final[str] = (
    "La URL figura en la lista negra activa de PhishTank, por lo que el "
    "análisis se eleva automáticamente a riesgo Alto."
)

#: Título y descripción del reporte aún no validado por la comunidad.
PHISHTANK_UNVERIFIED_TITLE: Final[str] = "Reporte no verificado en PhishTank"
PHISHTANK_UNVERIFIED_DESCRIPTION: Final[str] = (
    "La URL se encuentra registrada en la base de datos de PhishTank, pero su "
    "estado de verificación por la comunidad aún está pendiente."
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


def phishtank_unverified_evidence() -> EvidenceDTO:
    """Construye la evidencia de reporte pendiente de verificación (Opción B)."""
    return EvidenceDTO(
        rule_id=PHISHTANK_UNVERIFIED_RULE_ID,
        points=PHISHTANK_UNVERIFIED_POINTS,
        title=PHISHTANK_UNVERIFIED_TITLE,
        description=PHISHTANK_UNVERIFIED_DESCRIPTION,
    )


def build_evidences(
    results: Iterable[RuleResult],
    *,
    phishtank_match: bool = False,
    phishtank_unverified: bool = False,
) -> list[EvidenceDTO]:
    """Devuelve las evidencias de las reglas activadas, en orden de entrada.

    Args:
        results: Resultados de las reglas léxicas.
        phishtank_match: Si es ``True``, se añade al final la evidencia
            ``MATCH_PHISHTANK`` con 50 puntos.
        phishtank_unverified: Si es ``True`` y no hay coincidencia confirmada,
            se añade al final la evidencia ``PHISHTANK_UNVERIFIED`` con 15
            puntos. Ambas evidencias son mutuamente excluyentes.

    Returns:
        Evidencias léxicas activadas y, si aplica, la de reputación externa.
    """
    evidences = [to_evidence(result) for result in results if result.activated]
    if phishtank_match:
        evidences.append(phishtank_evidence())
    elif phishtank_unverified:
        evidences.append(phishtank_unverified_evidence())
    return evidences


__all__ = [
    "PHISHTANK_DESCRIPTION",
    "PHISHTANK_TITLE",
    "PHISHTANK_UNVERIFIED_DESCRIPTION",
    "PHISHTANK_UNVERIFIED_TITLE",
    "build_evidences",
    "phishtank_evidence",
    "phishtank_unverified_evidence",
    "to_evidence",
]
