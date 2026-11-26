"""Explicabilidad del clasificador lineal por grupos de evidencia (RF-604).

Cada característica legible ``clave`` aporta ``wᵢ · xᵢ`` al puntaje lineal.
:func:`explain` agrupa esas contribuciones con :func:`app.ml.features.feature_group`
y devuelve solo las positivas, que son las que justifican una elevación del
riesgo. El orden del diccionario es el del catálogo del adendo §6, para que el
mismo URL produzca siempre la misma estructura.

No hay efectos secundarios: si el modelo no está disponible se devuelve ``{}``.
"""

from __future__ import annotations

from collections.abc import Mapping

from app.ml.features import extract_feature_keys, extract_features, feature_group
from app.ml.model import MODEL_GROUPS, get_model


def contributions_by_group(url: str) -> dict[str, float]:
    """Devuelve la contribución firmada de cada grupo (positiva y negativa)."""
    model = get_model()
    if not model.available:
        return {}

    features = extract_features(url)
    keys = extract_feature_keys(url)
    result: dict[str, float] = dict.fromkeys(MODEL_GROUPS, 0.0)
    for index, value in features.items():
        weight = model.weights.get(index)
        if weight is None:
            continue
        key = keys.get(index)
        if key is None:  # colisión de CRC-32: se atribuye al grupo residual
            group = "ML_URL_SHAPE"
        else:
            group = feature_group(key)
        result[group] = result.get(group, 0.0) + weight * value
    return result


def explain(url: str) -> dict[str, float]:
    """Devuelve ``grupo → contribución positiva`` para una URL (RF-604)."""
    return {
        group: contribution
        for group, contribution in contributions_by_group(url).items()
        if contribution > 0.0
    }


def contributions_from_parts(
    features: Mapping[int, float], keys: Mapping[int, str]
) -> dict[str, float]:
    """Variante para pruebas: agrupa un vector hashed ya calculado."""
    model = get_model()
    if not model.available:
        return {}
    result: dict[str, float] = dict.fromkeys(MODEL_GROUPS, 0.0)
    for index, value in features.items():
        weight = model.weights.get(index)
        if weight is None:
            continue
        key = keys.get(index, "")
        group = feature_group(key) if key else "ML_URL_SHAPE"
        result[group] = result.get(group, 0.0) + weight * value
    return result


__all__ = ["contributions_by_group", "contributions_from_parts", "explain"]
