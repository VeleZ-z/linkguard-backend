"""DTOs del contrato de API de LinkGuard (sección 6 de los requisitos).

Estos esquemas congelan la interfaz pública de ``POST /api/v1/analyze``. Cualquier
cambio en sus campos o en sus restricciones constituye un cambio de contrato y
debe reflejarse primero en la especificación de requisitos.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class RiskLevel(StrEnum):
    """Nivel de riesgo asignado a la URL analizada (RF-302)."""

    BAJO = "Bajo"
    MEDIO = "Medio"
    ALTO = "Alto"


class PhishtankStatus(StrEnum):
    """Estado de la consulta de reputación externa (RF-404)."""

    AVAILABLE = "available"
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"
    CACHED = "cached"


class AnalyzeRequest(BaseModel):
    """Solicitud de análisis de una URL ingresada manualmente por el usuario."""

    url: str = Field(
        min_length=3,
        max_length=4096,
        description="URL a evaluar, entre 3 y 4096 caracteres.",
    )


class EvidenceDTO(BaseModel):
    """Evidencia individual que explica los puntos aportados por una regla."""

    rule_id: str = Field(
        description="Identificador de la regla que se activó (por ejemplo, F02_DIRECT_IP).",
    )
    points: int = Field(
        ge=0,
        description="Puntos sumados al puntaje de riesgo por esta evidencia.",
    )
    title: str = Field(
        description="Título técnico legible de la anomalía detectada.",
    )
    description: str = Field(
        description="Explicación en español neutro comprensible para el usuario final.",
    )


# Alias de compatibilidad con la nomenclatura ``Evidence`` de la especificación.
Evidence = EvidenceDTO


class AnalyzeResponse(BaseModel):
    """Respuesta del análisis con puntaje, nivel, evidencias y recomendación."""

    url_analyzed: str = Field(
        description="URL original tal como fue recibida del cliente.",
    )
    normalized_url: str = Field(
        description="URL resultante del pipeline de normalización sintáctica.",
    )
    score: int = Field(
        ge=0,
        le=100,
        description="Puntaje de riesgo ponderado, acotado entre 0 y 100 (RF-301).",
    )
    risk_level: RiskLevel = Field(
        description="Nivel de riesgo derivado del puntaje (RF-302).",
    )
    recommendation: str = Field(
        description="Recomendación operativa asociada al nivel de riesgo (RF-304).",
    )
    evidences: list[EvidenceDTO] = Field(
        description="Desglose de las reglas que aportaron puntos al puntaje (RF-303).",
    )
    phishtank_status: PhishtankStatus = Field(
        description="Estado de la consulta de reputación externa (RF-404).",
    )
    execution_time_ms: float = Field(
        ge=0.0,
        description="Tiempo total de ejecución del análisis, en milisegundos.",
    )


__all__ = [
    "AnalyzeRequest",
    "AnalyzeResponse",
    "Evidence",
    "EvidenceDTO",
    "PhishtankStatus",
    "RiskLevel",
]
