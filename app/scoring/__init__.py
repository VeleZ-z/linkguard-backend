"""Módulo 300: scoring, clasificación y explicabilidad (RF-301…304, RF-701…706)."""

from __future__ import annotations

from app.scoring.calibration import get_thresholds, piecewise_linear
from app.scoring.evidence import build_evidences, to_evidence
from app.scoring.recommendations import get_recommendation
from app.scoring.scorer import (
    MAX_SCORE,
    ScoreBreakdown,
    ScoringResult,
    calculate_score,
    classify_risk,
    distribute_ml_points,
    score_results,
    score_v3,
)

__all__ = [
    "MAX_SCORE",
    "ScoreBreakdown",
    "ScoringResult",
    "build_evidences",
    "calculate_score",
    "classify_risk",
    "distribute_ml_points",
    "get_recommendation",
    "get_thresholds",
    "piecewise_linear",
    "score_results",
    "score_v3",
    "to_evidence",
]
