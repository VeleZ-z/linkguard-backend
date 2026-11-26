"""Construcción del desglose de evidencias (RF-303, RF-405, RF-704…706).

Solo las reglas activadas generan evidencia y cada elemento conserva su
``rule_id``, puntos, título y descripción en es-419. Sobre la evidencia v2 se
añaden los grupos ML del adendo §6 y las señales de reputación local: coincidencia
exacta de URL, coincidencia por host y dominio de confianza (0 puntos).

La suma de puntos de las evidencias léxicas + ML es igual al puntaje previo a
reputación (``S_pre``), salvo el tope de 100 y el límite de la allowlist.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Final

from app.engine.models import RuleResult
from app.ml.model import MODEL_GROUPS
from app.schemas import EvidenceDTO
from app.scoring.calibration import piecewise_linear
from app.scoring.scorer import (
    FEED_HOST_POINTS,
    FEED_URL_POINTS,
    PHISHTANK_POINTS,
    PHISHTANK_RULE_ID,
    PHISHTANK_UNVERIFIED_POINTS,
    PHISHTANK_UNVERIFIED_RULE_ID,
    distribute_ml_points,
)

#: Título y descripción literales de la evidencia de reputación (RF-405).
PHISHTANK_TITLE: Final[str] = "Reporte en lista negra de PhishTank"
PHISHTANK_DESCRIPTION: Final[str] = (
    "La URL figura en la lista negra activa de PhishTank, por lo que el "
    "análisis se eleva automáticamente a riesgo Alto."
)

#: Título y descripción del reporte aún no validado por la comunidad.
PHISHTANK_UNVERIFIED_TITLE: Final[str] = "Reporte no verificado en PhishTank"
PHISHTANK_UNVERIFIED_DESCRIPTION: Final[str] = (
    "La URL se encuentra registrada en la base de datos de PhishTank, pero su "
    "estado de verificación por la comunidad aún está pendiente."
)

#: Catálogo de textos de los grupos explicativos del modelo (adendo §6).
ML_EVIDENCE_TEXTS: Final[dict[str, tuple[str, str]]] = {
    "ML_TLD_RISK": (
        "Extensión de dominio frecuente en phishing",
        "La extensión del dominio aparece con frecuencia en campañas de "
        "suplantación y elevó el puntaje del clasificador.",
    ),
    "ML_DOMAIN_SHAPE": (
        "Nombre de dominio aleatorio o atípico",
        "La forma del nombre registrable se parece a la de dominios generados "
        "automáticamente para campañas de phishing.",
    ),
    "ML_HOST_PATTERN": (
        "Patrones sospechosos en el nombre del host",
        "Los subdominios o tokens del host repiten patrones habituales en "
        "páginas de inicio de sesión falsas.",
    ),
    "ML_PATH_PATTERN": (
        "Ruta con patrones típicos de phishing",
        "La ruta o la consulta incluye segmentos y extensiones frecuentes en "
        "enlaces de suplantación.",
    ),
    "ML_BRAND_MISMATCH": (
        "Marca conocida en un dominio que no es el oficial",
        "El texto de una marca reconocida aparece fuera de su dominio "
        "legítimo, lo que suele indicar suplantación.",
    ),
    "ML_URL_SHAPE": (
        "Estructura general inusual",
        "La longitud, el uso de @, el puerto u otros rasgos de la URL elevan "
        "el riesgo estimado por el modelo.",
    ),
}

#: Evidencias de reputación local y allowlist (RF-803…RF-805).
FEED_URL_TITLE: Final[str] = "URL reportada en una lista de phishing"
FEED_URL_DESCRIPTION: Final[str] = (
    "La URL exacta figura en una lista local de enlaces reportados; por eso "
    "el análisis se eleva a riesgo Alto."
)
FEED_HOST_TITLE: Final[str] = "Dominio reportado en una lista de phishing"
FEED_HOST_DESCRIPTION: Final[str] = (
    "El host aparece en una lista local de dominios reportados; se aplica un piso de riesgo Medio."
)
TRUSTED_DOMAIN_TITLE: Final[str] = "Dominio de alta reputación"
TRUSTED_DOMAIN_DESCRIPTION: Final[str] = (
    "El dominio registrable pertenece a una lista de sitios confiables. El "
    "puntaje queda limitado a 30, salvo que exista una coincidencia exacta "
    "confirmada. Esta evidencia no suma puntos."
)


def to_evidence(result: RuleResult) -> EvidenceDTO:
    """Convierte un ``RuleResult`` en el DTO de evidencia del contrato."""
    return EvidenceDTO(
        rule_id=result.rule_id,
        points=result.points,
        title=result.title,
        description=result.description,
    )


def phishtank_evidence() -> EvidenceDTO:
    """Construye la evidencia de coincidencia en PhishTank (RF-405)."""
    return EvidenceDTO(
        rule_id=PHISHTANK_RULE_ID,
        points=PHISHTANK_POINTS,
        title=PHISHTANK_TITLE,
        description=PHISHTANK_DESCRIPTION,
    )


def phishtank_unverified_evidence() -> EvidenceDTO:
    """Construye la evidencia de reporte pendiente de verificación (Opción B)."""
    return EvidenceDTO(
        rule_id=PHISHTANK_UNVERIFIED_RULE_ID,
        points=PHISHTANK_UNVERIFIED_POINTS,
        title=PHISHTANK_UNVERIFIED_TITLE,
        description=PHISHTANK_UNVERIFIED_DESCRIPTION,
    )


def ml_evidence(group: str, points: int) -> EvidenceDTO:
    """Construye una evidencia ML con el texto del catálogo (RF-704, §6)."""
    title, description = ML_EVIDENCE_TEXTS.get(
        group,
        ("Patrón detectado por el clasificador", "El modelo elevó el riesgo de la URL."),
    )
    return EvidenceDTO(rule_id=group, points=points, title=title, description=description)


def feed_url_evidence() -> EvidenceDTO:
    """Construye la evidencia de coincidencia exacta en feed local (RF-803)."""
    return EvidenceDTO(
        rule_id="MATCH_FEED_URL",
        points=FEED_URL_POINTS,
        title=FEED_URL_TITLE,
        description=FEED_URL_DESCRIPTION,
    )


def feed_host_evidence() -> EvidenceDTO:
    """Construye la evidencia de coincidencia por host (RF-804)."""
    return EvidenceDTO(
        rule_id="MATCH_FEED_HOST",
        points=FEED_HOST_POINTS,
        title=FEED_HOST_TITLE,
        description=FEED_HOST_DESCRIPTION,
    )


def trusted_domain_evidence() -> EvidenceDTO:
    """Construye la evidencia informativa de allowlist (RF-705, 0 puntos)."""
    return EvidenceDTO(
        rule_id="TRUSTED_DOMAIN",
        points=0,
        title=TRUSTED_DOMAIN_TITLE,
        description=TRUSTED_DOMAIN_DESCRIPTION,
    )


def build_evidences(
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
) -> list[EvidenceDTO]:
    """Devuelve las evidencias activadas en orden: reglas, ML y reputación.

    Conserva la firma v2 cuando no se inyectan señales nuevas. Los parámetros
    adicionales son los mismos que :func:`app.scoring.scorer.score_v3`, de modo
    que puntaje y evidencias se calculan con idéntica precedencia.
    """
    activas = [to_evidence(result) for result in results if result.activated]
    s_rules = min(100, round(sum(evidence.points for evidence in activas)))
    puntos_ml = s_ml if s_ml is not None else (piecewise_linear(p) if p is not None else 0)
    delta = max(0, min(100, int(puntos_ml)) - s_rules)
    ml_points = distribute_ml_points(delta, ml_contributions)
    orden = {group: position for position, group in enumerate(MODEL_GROUPS)}
    ml_evidences = [
        ml_evidence(group, points)
        for group, points in sorted(
            ml_points.items(), key=lambda item: (-item[1], orden.get(item[0], 99), item[0])
        )
    ]

    exacta = feed_url or phishtank_match
    trusted = allowlisted and not abusable and not exacta
    aplica_pu = phishtank_unverified and not exacta
    aplica_fh = feed_host and not allowlisted and not abusable and not exacta

    evidencias: list[EvidenceDTO] = activas + ml_evidences
    if trusted:
        evidencias.append(trusted_domain_evidence())
    if feed_url:
        evidencias.append(feed_url_evidence())
    elif phishtank_match:
        evidencias.append(phishtank_evidence())
    elif aplica_pu:
        evidencias.append(phishtank_unverified_evidence())
    if aplica_fh:
        evidencias.append(feed_host_evidence())
    return evidencias


__all__ = [
    "FEED_HOST_DESCRIPTION",
    "FEED_HOST_TITLE",
    "FEED_URL_DESCRIPTION",
    "FEED_URL_TITLE",
    "ML_EVIDENCE_TEXTS",
    "PHISHTANK_DESCRIPTION",
    "PHISHTANK_TITLE",
    "PHISHTANK_UNVERIFIED_DESCRIPTION",
    "PHISHTANK_UNVERIFIED_TITLE",
    "TRUSTED_DOMAIN_DESCRIPTION",
    "TRUSTED_DOMAIN_TITLE",
    "build_evidences",
    "feed_host_evidence",
    "feed_url_evidence",
    "ml_evidence",
    "phishtank_evidence",
    "phishtank_unverified_evidence",
    "to_evidence",
    "trusted_domain_evidence",
]
