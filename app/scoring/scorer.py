"""Cálculo ponderado y clasificación del riesgo (RF-301, RF-302, RF-405).

El puntaje es la suma de los puntos de las reglas activadas, acotada a 100.
La clasificación usa las fronteras exactas del contrato: Bajo ``0–30``,
Medio ``31–69`` y Alto ``70–100``.

Reputación externa (PhishTank)
------------------------------
* **Coincidencia confirmada** (``phishtank_match``): +50 puntos y se fuerza el
  nivel ``Alto``, sin importar el puntaje léxico previo (RF-405).
* **Reporte no verificado** (``phishtank_unverified``): +15 puntos, pero el
  nivel se deriva del puntaje con las fronteras normales. Solo se aplica si no
  hay una coincidencia confirmada (Opción B).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final

from app.engine.models import RuleResult
from app.engine.weights import WEIGHTS
from app.schemas import RiskLevel

#: Tope superior del puntaje de riesgo (RF-301).
MAX_SCORE: Final[int] = 100

#: Fronteras inclusivas de los niveles de riesgo (RF-302).
LOW_MAX: Final[int] = 30
MEDIUM_MAX: Final[int] = 69

#: Identificador y peso de la evidencia de reputación confirmada (RF-405).
PHISHTANK_RULE_ID: Final[str] = "MATCH_PHISHTANK"
PHISHTANK_POINTS: Final[int] = WEIGHTS[PHISHTANK_RULE_ID]

#: Identificador y peso de la evidencia de reporte pendiente de verificación.
#: No forma parte de la matriz léxica F01–F11: es un peso fijo de reputación.
PHISHTANK_UNVERIFIED_RULE_ID: Final[str] = "PHISHTANK_UNVERIFIED"
PHISHTANK_UNVERIFIED_POINTS: Final[int] = 15


@dataclass(frozen=True, slots=True)
class ScoringResult:
    """Puntaje acotado y nivel de riesgo derivado."""

    score: int
    risk_level: RiskLevel


def calculate_score(
    results: Iterable[RuleResult],
    *,
    phishtank_match: bool = False,
    phishtank_unverified: bool = False,
) -> int:
    """Suma los puntos de las reglas activadas y acota el total a 100.

    Args:
        results: Resultados de las reglas léxicas.
        phishtank_match: Si PhishTank confirmó la URL en su lista negra,
            se añaden ``PHISHTANK_POINTS`` (+50) antes de acotar (RF-405).
        phishtank_unverified: Si la URL está reportada pero pendiente de
            verificación, se añaden 15 puntos. Se ignora cuando
            ``phishtank_match`` es ``True`` (la coincidencia confirmada tiene
            prioridad y no se duplica la penalización externa).

    Returns:
        Puntaje entero entre 0 y 100.
    """
    total = sum(result.points for result in results if result.activated)
    if phishtank_match:
        total += PHISHTANK_POINTS
    elif phishtank_unverified:
        total += PHISHTANK_UNVERIFIED_POINTS
    return min(MAX_SCORE, round(total))


def classify_risk(score: int) -> RiskLevel:
    """Mapea un puntaje 0–100 a ``Bajo``, ``Medio`` o ``Alto`` (RF-302).

    Args:
        score: Puntaje de riesgo ya acotado.

    Returns:
        Nivel de riesgo correspondiente a las fronteras del contrato.

    Raises:
        ValueError: Si ``score`` está fuera del rango 0–100.
    """
    if not 0 <= score <= MAX_SCORE:
        raise ValueError("El puntaje debe estar entre 0 y 100")
    if score <= LOW_MAX:
        return RiskLevel.BAJO
    if score <= MEDIUM_MAX:
        return RiskLevel.MEDIO
    return RiskLevel.ALTO


def score_results(
    results: Iterable[RuleResult],
    *,
    phishtank_match: bool = False,
    phishtank_unverified: bool = False,
) -> ScoringResult:
    """Calcula puntaje y nivel de riesgo en una sola operación.

    Args:
        results: Resultados de las reglas léxicas.
        phishtank_match: Si es ``True``, se suman 50 puntos y el nivel se
            fuerza a ``Alto`` con independencia del score léxico (RF-405).
        phishtank_unverified: Si es ``True`` y no hay match confirmado, se
            suman 15 puntos y el nivel se clasifica con las fronteras normales.

    Returns:
        ``ScoringResult`` con el puntaje acotado y el nivel resultante.
    """
    score = calculate_score(
        results,
        phishtank_match=phishtank_match,
        phishtank_unverified=phishtank_unverified,
    )
    risk_level = RiskLevel.ALTO if phishtank_match else classify_risk(score)
    return ScoringResult(score=score, risk_level=risk_level)


__all__ = [
    "LOW_MAX",
    "MAX_SCORE",
    "MEDIUM_MAX",
    "PHISHTANK_POINTS",
    "PHISHTANK_RULE_ID",
    "PHISHTANK_UNVERIFIED_POINTS",
    "PHISHTANK_UNVERIFIED_RULE_ID",
    "ScoringResult",
    "calculate_score",
    "classify_risk",
    "score_results",
]
