"""Endpoint de análisis de URLs (RF-301…RF-305, RF-401, RF-404).

El handler delega todo el pipeline en :func:`app.services.analyzer.analyze_url`
(normalización, reglas léxicas y reputación en paralelo) y emite el evento de
telemetría con la IP del cliente. Un fallo de PhishTank nunca produce HTTP 5xx:
la respuesta conserva el análisis léxico y el ``phishtank_status`` real.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.core.config import get_settings
from app.core.logging import log_analyze_event
from app.core.rate_limit import limiter
from app.schemas import AnalyzeRequest, AnalyzeResponse
from app.services import analyzer

router = APIRouter(tags=["analyze"])

#: Límite por IP tomado de la configuración (30/min por defecto).
RATE_LIMIT: str = f"{get_settings().RATE_LIMIT_PER_MINUTE}/minute"


@router.post(
    "/analyze",
    response_model=AnalyzeResponse,
    summary="Evalúa el riesgo sintáctico-léxico de una URL",
)
@limiter.limit(RATE_LIMIT)
async def analyze_endpoint(request: Request, payload: AnalyzeRequest) -> AnalyzeResponse:
    """Analiza la URL y devuelve el contrato §6 completo.

    Args:
        request: Petición HTTP (usada por el limitador y para obtener la IP).
        payload: DTO con la URL a evaluar (3–4096 caracteres).

    Returns:
        ``AnalyzeResponse`` con puntaje, nivel, evidencias, recomendación,
        ``phishtank_status`` y tiempo de ejecución.

    Raises:
        InvalidURLError: Si la entrada no es un enlace HTTP/HTTPS válido.
        URLTooLongError: Si tras sanitizar supera los 4096 caracteres.
    """
    response = await analyzer.analyze_url(payload.url)

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
