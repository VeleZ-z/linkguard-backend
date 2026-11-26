"""Cálculo de riesgo v2/v3 y clasificación por niveles (RF-301…303, RF-701…706).

El comportamiento v2 se conserva: las firmas públicas ``calculate_score``,
``score_results`` y ``classify_risk`` siguen aceptando las mismas llamadas y
devolviendo los mismos valores cuando no se inyectan señales nuevas. Sobre esa
base se añaden, todos como argumentos opcionales, las señales del adendo v3:

1. ``S_rules`` = score v2; ``S_ml = PL(p)``; ``S_pre = max(S_rules, S_ml)``.
2. Si ``S_ml > S_rules``, el delta se reparte por el método del mayor resto
   entre los tres grupos ML con mayor contribución positiva (RF-704).
3. Allowlist: ``min(score, 30)`` salvo abusable o coincidencia exacta (RF-705).
4. Feeds y PhishTank aplican las bonificaciones y pisos de nivel de §5.

Las evidencias se construyen en :mod:`app.scoring.evidence` con las mismas
señales; la suma de sus puntos iguala ``S_pre`` salvo el tope de 100 y la
allowlist, tal como exige RF-704.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Final

from app.engine.models import RuleResult
from app.engine.weights import WEIGHTS
from app.ml.model import MODEL_GROUPS
from app.schemas import RiskLevel
from app.scoring.calibration import piecewise_linear

#: Tope superior del puntaje de riesgo (RF-301).
MAX_SCORE: Final[int] = 100

#: Fronteras inclusivas de los niveles de riesgo (RF-302).
LOW_MAX: Final[int] = 30
MEDIUM_MAX: Final[int] = 69

#: Identificador y peso de la evidencia de reputación confirmada (RF-405).
PHISHTANK_RULE_ID: Final[str] = "MATCH_PHISHTANK"
PHISHTANK_POINTS: Final[int] = WEIGHTS[PHISHTANK_RULE_ID]

#: Identificador y peso del reporte pendiente de verificación (Opción B).
PHISHTANK_UNVERIFIED_RULE_ID: Final[str] = "PHISHTANK_UNVERIFIED"
PHISHTANK_UNVERIFIED_POINTS: Final[int] = 15

#: Puntos y piso de nivel de las señales locales (RF-803/RF-804).
FEED_URL_POINTS: Final[int] = 50
FEED_HOST_POINTS: Final[int] = 40
ALLOWLIST_CAP: Final[int] = 30

#: Orden de nivel para aplicar el piso ``>= Medio`` sin cambiar el contrato.
_LEVEL_ORDER: tuple[RiskLevel, ...] = (RiskLevel.BAJO, RiskLevel.MEDIO, RiskLevel.ALTO)
_MAX_ML_EVIDENCES: int = 3


@dataclass(frozen=True, slots=True)
class ScoringResult:
    """Puntaje acotado y nivel de riesgo derivado."""

    score: int
    risk_level: RiskLevel


@dataclass(frozen=True, slots=True)
class ScoreBreakdown:
    """Desglose completo del algoritmo normativo de §5 (RF-701…706)."""

    score: int
    risk_level: RiskLevel
    s_rules: int
    s_ml: int
    s_pre: int
    ml_delta: int
    ml_points: dict[str, int]
    trusted: bool
    feed_url: bool
    feed_host: bool
    phishtank_match: bool
    phishtank_unverified: bool


def _s_rules(results: Iterable[RuleResult]) -> int:
    """Score v2: suma de reglas activas, redondeada y acotada a 100."""
    total = sum(result.points for result in results if result.activated)
    return min(MAX_SCORE, round(total))


def distribute_ml_points(
    delta: int,
    contributions: Mapping[str, float] | None = None,
) -> dict[str, int]:
    """Reparte ``delta`` puntos por el método del mayor resto (RF-704).

    Solo intervienen los tres grupos con mayor contribución positiva: así se
    cumplen simultáneamente el límite de evidencias y la invariante de que sus
    puntos suman el delta completo. Los empates se resuelven por el orden del
    catálogo del adendo §6, luego por nombre, para ser determinista.

    Args:
        delta: Puntos a repartir (``S_ml - S_rules``).
        contributions: Contribución positiva por grupo. Si es None o no hay
            contribuciones positivas, se reparte a partes iguales entre los seis
            grupos del catálogo (caso de modelo sin explicación).

    Returns:
        ``grupo → puntos``, sin incluir grupos con menos de un punto.
    """
    if delta <= 0:
        return {}

    positives: list[tuple[str, float]] = []
    if contributions:
        positives = [
            (str(group), float(value))
            for group, value in contributions.items()
            if float(value) > 0.0
        ]
    if not positives:
        positives = [(group, 1.0) for group in MODEL_GROUPS]

    def _sort_key(item: tuple[str, float]) -> tuple[float, int, str]:
        group, value = item
        order = MODEL_GROUPS.index(group) if group in MODEL_GROUPS else len(MODEL_GROUPS)
        return -value, order, group

    selected = sorted(positives, key=_sort_key)[:_MAX_ML_EVIDENCES]
    weight_total = sum(weight for _, weight in selected)
    raw = [delta * weight / weight_total for _, weight in selected]
    assigned = [int(value) for value in raw]
    pending = delta - sum(assigned)
    order = sorted(range(len(selected)), key=lambda i: (-(raw[i] - assigned[i]), i))
    for index in order[:pending]:
        assigned[index] += 1
    return {
        group: points for (group, _), points in zip(selected, assigned, strict=True) if points >= 1
    }


def score_v3(
    results: Iterable[RuleResult],
    *,
    phishtank_match: bool = False,
    phishtank_unverified: bool = False,
    s_ml: int | None = None,
    p: float | None = None,
    allowlisted: bool = False,
    abusable: bool = False,
    feed_url: bool = False,
    feed_host: bool = False,
    ml_contributions: Mapping[str, float] | None = None,
) -> ScoreBreakdown:
    """Ejecuta el algoritmo normativo §5 y devuelve su desglose.

    Args:
        results: Resultados de las reglas léxicas v2.
        phishtank_match: Coincidencia confirmada en PhishTank (RF-405).
        phishtank_unverified: Reporte pendiente de verificación (Opción B).
        s_ml: Puntaje ML ya calculado. Si se omite, se deriva de ``p`` con PL.
        p: Probabilidad del modelo; se usa solo si no se da ``s_ml``.
        allowlisted: Dominio registrable en allowlist (RF-705).
        abusable: Servicio abusable (RF-503); bloquea la allowlist y el host feed.
        feed_url: Coincidencia exacta de URL en feed local (RF-803).
        feed_host: Coincidencia por host en feed local (RF-804).
        ml_contributions: Contribuciones por grupo para el reparto de RF-704.

    Returns:
        :class:`ScoreBreakdown` con score, nivel y todas las señales aplicadas.
    """
    s_rules = _s_rules(results)
    puntos_ml = s_ml if s_ml is not None else (piecewise_linear(p) if p is not None else 0)
    s_ml_efectivo = max(0, min(MAX_SCORE, int(puntos_ml)))
    s_pre = max(s_rules, s_ml_efectivo)
    delta = s_ml_efectivo - s_rules
    ml_points = distribute_ml_points(delta, ml_contributions) if delta > 0 else {}

    # Precedencia: FU > A > FH > modelo/reglas (§5, RF-803 y RF-705).
    exacta = feed_url or phishtank_match
    trusted = allowlisted and not abusable and not exacta
    aplica_pu = phishtank_unverified and not exacta
    aplica_fh = feed_host and not allowlisted and not abusable and not exacta

    score = min(s_pre, ALLOWLIST_CAP) if trusted else s_pre
    if exacta:
        score = min(MAX_SCORE, score + FEED_URL_POINTS)
    elif aplica_pu:
        score = min(MAX_SCORE, score + PHISHTANK_UNVERIFIED_POINTS)
    if aplica_fh:
        score = min(MAX_SCORE, score + FEED_HOST_POINTS)

    nivel = classify_risk(score)
    if exacta:
        nivel = RiskLevel.ALTO
    if aplica_fh:
        indice = max(_LEVEL_ORDER.index(nivel), _LEVEL_ORDER.index(RiskLevel.MEDIO))
        nivel = _LEVEL_ORDER[indice]

    return ScoreBreakdown(
        score=score,
        risk_level=nivel,
        s_rules=s_rules,
        s_ml=s_ml_efectivo,
        s_pre=s_pre,
        ml_delta=delta,
        ml_points=ml_points,
        trusted=trusted,
        feed_url=feed_url,
        feed_host=aplica_fh,
        phishtank_match=phishtank_match,
        phishtank_unverified=aplica_pu,
    )


def calculate_score(
    results: Iterable[RuleResult],
    *,
    phishtank_match: bool = False,
    phishtank_unverified: bool = False,
    s_ml: int | None = None,
    p: float | None = None,
    allowlisted: bool = False,
    abusable: bool = False,
    feed_url: bool = False,
    feed_host: bool = False,
    ml_contributions: Mapping[str, float] | None = None,
) -> int:
    """Suma las reglas activadas, integra el modelo y acota el total a 100.

    Sin señales v3 mantiene exactamente el comportamiento v2 (RF-301/RF-405).
    """
    return score_v3(
        results,
        phishtank_match=phishtank_match,
        phishtank_unverified=phishtank_unverified,
        s_ml=s_ml,
        p=p,
        allowlisted=allowlisted,
        abusable=abusable,
        feed_url=feed_url,
        feed_host=feed_host,
        ml_contributions=ml_contributions,
    ).score


def classify_risk(score: int) -> RiskLevel:
    """Mapea un puntaje 0–100 a ``Bajo``, ``Medio`` o ``Alto`` (RF-302).

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
    s_ml: int | None = None,
    p: float | None = None,
    allowlisted: bool = False,
    abusable: bool = False,
    feed_url: bool = False,
    feed_host: bool = False,
    ml_contributions: Mapping[str, float] | None = None,
) -> ScoringResult:
    """Calcula puntaje y nivel en una operación, conservando la API v2."""
    desglose = score_v3(
        results,
        phishtank_match=phishtank_match,
        phishtank_unverified=phishtank_unverified,
        s_ml=s_ml,
        p=p,
        allowlisted=allowlisted,
        abusable=abusable,
        feed_url=feed_url,
        feed_host=feed_host,
        ml_contributions=ml_contributions,
    )
    return ScoringResult(score=desglose.score, risk_level=desglose.risk_level)


__all__ = [
    "ALLOWLIST_CAP",
    "FEED_HOST_POINTS",
    "FEED_URL_POINTS",
    "LOW_MAX",
    "MAX_SCORE",
    "MEDIUM_MAX",
    "PHISHTANK_POINTS",
    "PHISHTANK_RULE_ID",
    "PHISHTANK_UNVERIFIED_POINTS",
    "PHISHTANK_UNVERIFIED_RULE_ID",
    "ScoreBreakdown",
    "ScoringResult",
    "calculate_score",
    "classify_risk",
    "distribute_ml_points",
    "score_results",
    "score_v3",
]
