"""Módulo de clasificador léxico lineal (Hito 5, RF-601/RF-602/RF-604)."""

from app.ml.explain import contributions_by_group, explain
from app.ml.features import (
    N_FEATURES,
    extract_feature_keys,
    extract_features,
    extract_labelled,
    feature_group,
    hash_feature,
)
from app.ml.model import (
    MODEL_GROUPS,
    MODEL_PATH,
    LinearModel,
    clear_model_cache,
    get_model,
    load_model,
    model_score,
    predict,
)

__all__ = [
    "MODEL_GROUPS",
    "MODEL_PATH",
    "N_FEATURES",
    "LinearModel",
    "clear_model_cache",
    "contributions_by_group",
    "explain",
    "extract_feature_keys",
    "extract_features",
    "extract_labelled",
    "feature_group",
    "get_model",
    "hash_feature",
    "load_model",
    "model_score",
    "predict",
]
