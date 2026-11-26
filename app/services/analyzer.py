"""Orquestador concurrente del análisis de URLs (RF-401, RF-405, RNF-104).

Coordina, en paralelo mediante :func:`asyncio.gather`, dos tareas:

1. **Local:** reglas léxicas v2, inferencia del modelo lineal, explicabilidad y
   señales de reputación de los artefactos en memoria.
2. **Externa:** consulta de reputación a PhishTank.

Cada componente se degrada de forma aislada: un fallo del modelo, de un
artefacto o de la red no impide responder con el resto de señales y **nunca**
produce HTTP 500. El scoring v3 se activa con ``ENABLE_V3_SCORING`` (guardia de
rollout hasta H5-T15); con el valor por defecto se conserva el comportamiento
v2 y todas las expectativas de las suites heredadas.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from time import perf_counter

from app.clients.phishtank import (
    PhishtankClient,
    PhishtankResult,
    get_phishtank_client,
)
from app.core.config import get_settings
from app.core.logging import get_logger
from app.engine.models import ParsedURL, RuleResult
from app.engine.pipeline import run_rules
from app.ml import contributions_by_group, predict
from app.normalization import normalize
from app.reputation import ReputationSignals, get_reputation
from app.schemas import AnalyzeResponse, EvidenceDTO, PhishtankStatus, RiskLevel
from app.scoring.calibration import piecewise_linear
from app.scoring.evidence import build_evidences
from app.scoring.recommendations import get_recommendation
from app.scoring.scorer import score_results, score_v3

logger = get_logger()


@dataclass(frozen=True, slots=True)
class _LocalSignals:
    """Resultado de la tarea local: reglas, probabilidad y reputación."""

    rules: list[RuleResult]
    probability: float
    contributions: dict[str, float]
    reputation: ReputationSignals


def _fallo(componente: str, exc: Exception) -> None:
    """Registra una degradación sin incluir la URL analizada en el log."""
    logger.warning("Fallo de %s: %s", componente, type(exc).__name__)


async def _run_local(parsed: ParsedURL) -> _LocalSignals:
    """Ejecuta los componentes locales en un hilo, con degradación por señal."""

    def _compute() -> _LocalSignals:
        try:
            rules = run_rules(parsed)
        except Exception as exc:
            _fallo("reglas léxicas", exc)
            rules = []

        try:
            probability = predict(parsed.normalized_url)
        except Exception as exc:
            _fallo("modelo lineal", exc)
            probability = 0.0

        try:
            contributions = contributions_by_group(parsed.normalized_url)
        except Exception as exc:
            _fallo("explicabilidad", exc)
            contributions = {}

        try:
            reputation = get_reputation(parsed)
        except Exception as exc:
            _fallo("reputación local", exc)
            reputation = ReputationSignals()

        return _LocalSignals(
            rules=rules,
            probability=probability,
            contributions=contributions,
            reputation=reputation,
        )

    return await asyncio.to_thread(_compute)


async def _check_reputation(client: PhishtankClient, url: str) -> PhishtankResult:
    """Consulta la reputación degradando a ``unavailable`` ante cualquier fallo.

    Si ``PHISHTANK_ENABLED`` es ``False`` la consulta externa se omite por
    completo y se responde ``unavailable``; así los benchmarks locales y los
    despliegues sin reputación no abren conexiones (RNF-101, RNF-104).

    El cliente ya captura los errores de red previstos (RF-404). Esta guarda
    adicional garantiza que ni siquiera un fallo inesperado del cliente pueda
    propagarse como HTTP 500 (RNF-104).
    """
    if not get_settings().PHISHTANK_ENABLED:
        return PhishtankResult(is_match=False, status=PhishtankStatus.UNAVAILABLE)

    try:
        return await client.check_url(url)
    except Exception as exc:  # degradación elegante obligatoria (RNF-104)
        _fallo("PhishTank", exc)
        return PhishtankResult(is_match=False, status=PhishtankStatus.UNAVAILABLE)


def _score(
    local: _LocalSignals,
    reputation: PhishtankResult,
    *,
    v3: bool,
) -> tuple[int, RiskLevel, list[EvidenceDTO]]:
    """Calcula puntaje, nivel y evidencias con la precedencia normativa."""
    if not v3:
        scoring = score_results(
            local.rules,
            phishtank_match=reputation.is_match,
            phishtank_unverified=reputation.is_unverified,
        )
        evidences = build_evidences(
            local.rules,
            phishtank_match=reputation.is_match,
            phishtank_unverified=reputation.is_unverified,
        )
        return scoring.score, scoring.risk_level, evidences

    señales = local.reputation
    desglose = score_v3(
        local.rules,
        phishtank_match=reputation.is_match,
        phishtank_unverified=reputation.is_unverified,
        s_ml=piecewise_linear(local.probability),
        allowlisted=señales.allowlisted,
        abusable=señales.abusable,
        feed_url=señales.feed_url,
        feed_host=señales.feed_host,
        ml_contributions=local.contributions,
    )
    evidences = build_evidences(
        local.rules,
        phishtank_match=reputation.is_match,
        phishtank_unverified=reputation.is_unverified,
        s_ml=piecewise_linear(local.probability),
        allowlisted=señales.allowlisted,
        abusable=señales.abusable,
        feed_url=señales.feed_url,
        feed_host=señales.feed_host,
        ml_contributions=local.contributions,
    )
    return desglose.score, desglose.risk_level, evidences


async def analyze_url(url: str, *, client: PhishtankClient | None = None) -> AnalyzeResponse:
    """Ejecuta el análisis completo de una URL y devuelve el contrato §6.

    Args:
        url: URL original tal como la ingresó el cliente.
        client: Cliente de reputación inyectable; por defecto el del proceso.

    Returns:
        ``AnalyzeResponse`` con puntaje, nivel, evidencias, recomendación,
        ``phishtank_status`` real y tiempo total en milisegundos. Un reporte
        de PhishTank pendiente de verificación suma 15 puntos y se clasifica
        con las fronteras normales (Opción B).

    Raises:
        InvalidURLError: Si la URL no es un enlace HTTP/HTTPS válido.
        URLTooLongError: Si tras la sanitización supera los 4096 caracteres.
    """
    started_at = perf_counter()
    parsed = normalize(url)
    phishtank_client = client if client is not None else get_phishtank_client()

    local, reputation = await asyncio.gather(
        _run_local(parsed),
        _check_reputation(phishtank_client, parsed.normalized_url),
    )

    score, nivel, evidencias = _score(
        local,
        reputation,
        v3=get_settings().ENABLE_V3_SCORING,
    )
    execution_time_ms = round((perf_counter() - started_at) * 1000, 2)

    return AnalyzeResponse(
        url_analyzed=url,
        normalized_url=parsed.normalized_url,
        score=score,
        risk_level=nivel,
        recommendation=get_recommendation(nivel),
        evidences=evidencias,
        phishtank_status=reputation.status,
        execution_time_ms=execution_time_ms,
    )


__all__ = ["analyze_url"]
