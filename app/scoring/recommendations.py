"""Recomendaciones operativas por nivel de riesgo (RF-304, RNF-106).

Los textos son los publicados literalmente en la especificación de
requisitos y no deben reescribirse.
"""

from __future__ import annotations

from typing import Final

from app.schemas import RiskLevel

RECOMMENDATION_BAJO: Final[str] = (
    "No se detectaron anomalías estructurales severas ni reportes en listas "
    "negras. Mantenga las precauciones habituales al navegar."
)
RECOMMENDATION_MEDIO: Final[str] = (
    "El enlace presenta características inusuales o sospechosas (ej. longitud "
    "elevada, palabras clave o acortadores). Verifique la identidad del "
    "remitente antes de interactuar."
)
RECOMMENDATION_ALTO: Final[str] = (
    "Enlace altamente peligroso o reportado activamente como sospechoso. Se "
    "recomienda NO hacer clic, NO ingresar credenciales ni compartir "
    "información confidencial."
)

#: Recomendación exacta asociada a cada nivel de riesgo.
RECOMMENDATIONS: Final[dict[RiskLevel, str]] = {
    RiskLevel.BAJO: RECOMMENDATION_BAJO,
    RiskLevel.MEDIO: RECOMMENDATION_MEDIO,
    RiskLevel.ALTO: RECOMMENDATION_ALTO,
}


def get_recommendation(risk_level: RiskLevel) -> str:
    """Retorna la recomendación operativa del nivel indicado (RF-304)."""
    return RECOMMENDATIONS[risk_level]


__all__ = [
    "RECOMMENDATIONS",
    "RECOMMENDATION_ALTO",
    "RECOMMENDATION_BAJO",
    "RECOMMENDATION_MEDIO",
    "get_recommendation",
]
