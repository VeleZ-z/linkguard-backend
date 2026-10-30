"""Orquestador concurrente del análisis de URLs (RF-401, RF-405, RNF-104).

Coordina la normalización, el motor léxico local y la consulta de reputación
externa en paralelo mediante :func:`asyncio.gather`. La reputación nunca
bloquea el resultado: si PhishTank falla, el análisis léxico se entrega igual
con ``phishtank_status`` en ``timeout`` o ``unavailable``.
"""

from __future__ import annotations

import asyncio
from time import perf_counter

from app.clients.phishtank import (
    PhishtankClient,
    PhishtankResult,
    get_phishtank_client,
)
from app.core.logging import get_logger
from app.engine.models import ParsedURL, RuleResult
from app.engine.pipeline import run_rules
from app.normalization import normalize
from app.schemas import AnalyzeResponse, PhishtankStatus
from app.scoring.evidence import build_evidences
from app.scoring.recommendations import get_recommendation
from app.scoring.scorer import score_results

logger = get_logger()


async def _run_lexical(parsed: ParsedURL) -> list[RuleResult]:
    """Ejecuta las reglas léxicas fuera del event loop.

    Las reglas son CPU-bound y puras; delegarlas a un hilo evita que un
    análisis pesado retrase la resolución de la consulta de reputación.
    """
    return await asyncio.to_thread(run_rules, parsed)


async def _check_reputation(client: PhishtankClient, url: str) -> PhishtankResult:
    """Consulta la reputación degradando a ``unavailable`` ante cualquier fallo.

    El cliente ya captura los errores de red previstos (RF-404). Esta guarda
    adicional garantiza que ni siquiera un fallo inesperado del cliente pueda
    propagarse como HTTP 500 (RNF-104).
    """
    try:
        return await client.check_url(url)
    except Exception as exc:  # degradación elegante obligatoria (RNF-104)
        logger.warning(
            "Fallo inesperado al consultar PhishTank: %s",
            type(exc).__name__,
        )
        return PhishtankResult(is_match=False, status=PhishtankStatus.UNAVAILABLE)


async def analyze_url(url: str, *, client: PhishtankClient | None = None) -> AnalyzeResponse:
    """Ejecuta el análisis completo de una URL y devuelve el contrato §6.

    Args:
        url: URL original tal como la ingresó el cliente.
        client: Cliente de reputación inyectable; por defecto el del proceso.

    Returns:
        ``AnalyzeResponse`` con puntaje, nivel, evidencias, recomendación,
        ``phishtank_status`` real y tiempo total en milisegundos.

    Raises:
        InvalidURLError: Si la URL no es un enlace HTTP/HTTPS válido.
        URLTooLongError: Si tras la sanitización supera los 4096 caracteres.
    """
    started_at = perf_counter()
    parsed = normalize(url)
    phishtank_client = client if client is not None else get_phishtank_client()

    results, reputation = await asyncio.gather(
        _run_lexical(parsed),
        _check_reputation(phishtank_client, parsed.normalized_url),
    )

    scoring = score_results(results, phishtank_match=reputation.is_match)
    evidences = build_evidences(results, phishtank_match=reputation.is_match)
    execution_time_ms = round((perf_counter() - started_at) * 1000, 2)

    return AnalyzeResponse(
        url_analyzed=url,
        normalized_url=parsed.normalized_url,
        score=scoring.score,
        risk_level=scoring.risk_level,
        recommendation=get_recommendation(scoring.risk_level),
        evidences=evidences,
        phishtank_status=reputation.status,
        execution_time_ms=execution_time_ms,
    )


__all__ = ["analyze_url"]
