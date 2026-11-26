"""Calibración del puntaje ML: nudos PL y umbrales efectivos (RF-603/RF-702).

La función lineal por tramos transforma la probabilidad ``p`` del modelo en
puntos, con nudos ``(0,0)``, ``(t_medio,31)``, ``(t_alto,70)`` y ``(1,100)``.
Los umbrales se leen del artefacto calibrado y pueden sobrescribirse con
``MODEL_THRESHOLD_MEDIO`` / ``MODEL_THRESHOLD_ALTO`` sin recompilar.
"""

from __future__ import annotations

from app.core.config import get_settings
from app.ml.model import FALLBACK_THRESHOLDS, get_model

#: Puntos asignados a los nudos ``(0, t_medio, t_alto, 1)`` del adendo §5 (RF-702).
PUNTOS_NUDOS: tuple[int, int, int, int] = (0, 31, 70, 100)


def get_thresholds() -> tuple[float, float]:
    """Devuelve ``(t_medio, t_alto)`` efectivos, con validación de orden."""
    settings = get_settings()
    modelo = get_model()
    medio = settings.MODEL_THRESHOLD_MEDIO
    alto = settings.MODEL_THRESHOLD_ALTO
    t_medio = float(medio) if medio is not None else modelo.threshold("medio")
    t_alto = float(alto) if alto is not None else modelo.threshold("alto")

    if not 0.0 < t_medio < t_alto < 1.0:
        t_medio, t_alto = FALLBACK_THRESHOLDS
    return t_medio, t_alto


def piecewise_linear(
    probability: float,
    *,
    t_medio: float | None = None,
    t_alto: float | None = None,
) -> int:
    """Convierte ``p`` en puntos mediante la PL normativa de RF-702.

    Args:
        probability: Probabilidad del modelo, recortada al intervalo ``[0,1]``.
        t_medio: Umbral del primer nudo; por defecto el efectivo (RF-603).
        t_alto: Umbral del segundo nudo; por defecto el efectivo (RF-603).

    Returns:
        Entero entre 0 y 100. En los nudos devuelve exactamente 0, 31, 70 y 100.
    """
    if t_medio is None or t_alto is None:
        umbral_medio, umbral_alto = get_thresholds()
        t_medio = umbral_medio if t_medio is None else t_medio
        t_alto = umbral_alto if t_alto is None else t_alto

    if not 0.0 < t_medio < t_alto < 1.0:
        t_medio, t_alto = FALLBACK_THRESHOLDS

    p = min(1.0, max(0.0, float(probability)))
    if p <= t_medio:
        puntos = 31.0 * p / t_medio
    elif p <= t_alto:
        puntos = 31.0 + 39.0 * (p - t_medio) / (t_alto - t_medio)
    else:
        puntos = 70.0 + 30.0 * (p - t_alto) / (1.0 - t_alto)
    return max(0, min(100, int(round(puntos))))


def s_ml_from_probability(probability: float) -> int:
    """Atajo para ``piecewise_linear`` con los umbrales efectivos."""
    return piecewise_linear(probability)


__all__ = [
    "PUNTOS_NUDOS",
    "get_thresholds",
    "piecewise_linear",
    "s_ml_from_probability",
]
