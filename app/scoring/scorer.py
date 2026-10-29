"""Cálculo ponderado y clasificación del riesgo (RF-301, RF-302).

El puntaje es la suma de los puntos de las reglas activadas, acotada a 100.
La clasificación usa las fronteras exactas del contrato: Bajo ``0–30``,
Medio ``31–69`` y Alto ``70–100``.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final

from app.engine.models import RuleResult
from app.schemas import RiskLevel

#: Tope superior del puntaje de riesgo (RF-301).
MAX_SCORE: Final[int] = 100

#: Fronteras inclusivas de los niveles de riesgo (RF-302).
LOW_MAX: Final[int] = 30
MEDIUM_MAX: Final[int] = 69


@dataclass(frozen=True, slots=True)
class ScoringResult:
    """Puntaje acotado y nivel de riesgo derivado."""

    score: int
    risk_level: RiskLevel


def calculate_score(results: Iterable[RuleResult]) -> int:
    """Suma los puntos de las reglas activadas y acota el total a 100.

    Args:
        results: Resultados de las reglas léxicas.

    Returns:
        Puntaje entero entre 0 y 100.
    """
    total = sum(result.points for result in results if result.activated)
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


def score_results(results: Iterable[RuleResult]) -> ScoringResult:
    """Calcula puntaje y nivel de riesgo en una sola operación."""
    score = calculate_score(results)
    return ScoringResult(score=score, risk_level=classify_risk(score))


__all__ = [
    "LOW_MAX",
    "MAX_SCORE",
    "MEDIUM_MAX",
    "ScoringResult",
    "calculate_score",
    "classify_risk",
    "score_results",
]
