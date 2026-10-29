"""Módulo 300: scoring, clasificación y explicabilidad (RF-301…RF-304)."""

from __future__ import annotations

from app.scoring.evidence import build_evidences, to_evidence
from app.scoring.recommendations import get_recommendation
from app.scoring.scorer import (
    MAX_SCORE,
    ScoringResult,
    calculate_score,
    classify_risk,
    score_results,
)

__all__ = [
    "MAX_SCORE",
    "ScoringResult",
    "build_evidences",
    "calculate_score",
    "classify_risk",
    "get_recommendation",
    "score_results",
    "to_evidence",
]
