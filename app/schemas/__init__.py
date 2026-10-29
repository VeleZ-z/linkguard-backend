"""Esquemas Pydantic que conforman el contrato de API de LinkGuard."""

from __future__ import annotations

from app.schemas.analyze import (
    AnalyzeRequest,
    AnalyzeResponse,
    Evidence,
    EvidenceDTO,
    PhishtankStatus,
    RiskLevel,
)

__all__ = [
    "AnalyzeRequest",
    "AnalyzeResponse",
    "Evidence",
    "EvidenceDTO",
    "PhishtankStatus",
    "RiskLevel",
]
