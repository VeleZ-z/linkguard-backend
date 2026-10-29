"""Endpoint de análisis de URLs (RF-301…RF-304).

Orquesta normalización → reglas léxicas → scoring → evidencias y
recomendación. El contrato §6 se mantiene intacto; PhishTank permanece en
``unavailable`` hasta el Hito 3.
"""

from __future__ import annotations

from time import perf_counter

from fastapi import APIRouter, Request

from app.core.config import get_settings
from app.core.logging import log_analyze_event
from app.core.rate_limit import limiter
from app.engine.pipeline import run_rules
from app.normalization import normalize
from app.schemas import AnalyzeRequest, AnalyzeResponse, PhishtankStatus
from app.scoring.evidence import build_evidences
from app.scoring.recommendations import get_recommendation
from app.scoring.scorer import calculate_score, classify_risk

router = APIRouter(tags=["analyze"])

#: Límite por IP tomado de la configuración (30/min por defecto).
RATE_LIMIT: str = f"{get_settings().RATE_LIMIT_PER_MINUTE}/minute"


@router.post(
    "/analyze",
    response_model=AnalyzeResponse,
    summary="Evalúa el riesgo sintáctico-léxico de una URL",
)
@limiter.limit(RATE_LIMIT)
async def analyze_url(request: Request, payload: AnalyzeRequest) -> AnalyzeResponse:
    """Normaliza la URL, ejecuta las reglas y devuelve el contrato §6.

    Args:
        request: Petición HTTP (usada por el limitador y para obtener la IP).
        payload: DTO con la URL a evaluar (3–4096 caracteres).

    Returns:
        ``AnalyzeResponse`` con puntaje, nivel, evidencias y recomendación.

    Raises:
        InvalidURLError: Si la entrada no es un enlace HTTP/HTTPS válido.
        URLTooLongError: Si tras sanitizar supera los 4096 caracteres.
    """
    started_at = perf_counter()
    parsed = normalize(payload.url)
    results = run_rules(parsed)
    score = calculate_score(results)
    risk_level = classify_risk(score)
    evidences = build_evidences(results)
    execution_time_ms = round((perf_counter() - started_at) * 1000, 2)

    response = AnalyzeResponse(
        url_analyzed=payload.url,
        normalized_url=parsed.normalized_url,
        score=score,
        risk_level=risk_level,
        recommendation=get_recommendation(risk_level),
        evidences=evidences,
        phishtank_status=PhishtankStatus.UNAVAILABLE,
        execution_time_ms=execution_time_ms,
    )

    log_analyze_event(
        url=payload.url,
        client_ip=request.client.host if request.client else None,
        score=response.score,
        risk_level=response.risk_level.value,
        phishtank_status=response.phishtank_status.value,
        rules_activated_count=len(response.evidences),
        execution_time_ms=response.execution_time_ms,
    )
    return response


__all__ = ["router"]
