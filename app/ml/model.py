"""Inferencia del clasificador lineal en Python puro (RF-602, RNF-109).

El artefacto ``model_v1.json`` se lee **una sola vez** por proceso y se guarda
en una instancia :class:`LinearModel` en memoria. No se importan NumPy ni
scikit-learn: la predicción es ``p = σ(bias + Σ wᵢxᵢ)`` sobre el vector hashed
que produce :func:`app.ml.features.extract_features`.

Si el JSON falta, está corrupto o no tiene el esquema esperado, se devuelve un
modelo deshabilitado (``available=False``) que predice ``0.0``. El servicio
sigue respondiendo HTTP 200 con el puntaje de las reglas v2 (RNF-107/RNF-104).
"""

from __future__ import annotations

import json
import logging
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.ml.features import extract_features

_log = logging.getLogger("linkguard.ml")

#: Artefacto de solo lectura incluido en la imagen (RF-602).
MODEL_PATH: Path = Path(__file__).resolve().parents[1] / "engine" / "data" / "model_v1.json"

#: Umbrales de reserva si el artefacto no está disponible (RF-603). No son
#: secretos: son las constantes calibradas y publicadas en el informe v1.
FALLBACK_THRESHOLDS: tuple[float, float] = (0.5378482329750933, 0.8541564782634935)

#: Catálogo de grupos de explicabilidad del adendo §6, en orden estable.
MODEL_GROUPS: tuple[str, ...] = (
    "ML_TLD_RISK",
    "ML_DOMAIN_SHAPE",
    "ML_HOST_PATTERN",
    "ML_PATH_PATTERN",
    "ML_BRAND_MISMATCH",
    "ML_URL_SHAPE",
)


def sigmoid(value: float) -> float:
    """Sigmoide numéricamente estable, sin dependencias externas."""
    if value >= 0.0:
        return 1.0 / (1.0 + math.exp(-value))
    exp_value = math.exp(value)
    return exp_value / (1.0 + exp_value)


@dataclass(frozen=True, slots=True)
class LinearModel:
    """Modelo lineal hashed listo para inferir.

    Los diccionarios se conservan como ``dict`` interno: solo se leen durante
    la inferencia y nunca se mutan en producción (RNF-103).
    """

    version: str = ""
    feature_spec_version: str = ""
    n_features: int = 0
    bias: float = 0.0
    weights: dict[int, float] = field(default_factory=dict)
    thresholds: dict[str, float] = field(default_factory=dict)
    trained_at: str = ""
    data_manifest: dict[str, Any] = field(default_factory=dict)
    available: bool = False

    def score(self, url: str) -> float:
        """Devuelve la suma ``bias + Σ wᵢxᵢ`` de una URL (sin sigmoide)."""
        return self.score_features(extract_features(url))

    def score_features(self, features: Mapping[int, float]) -> float:
        """Devuelve la puntuación lineal de un vector hashed ya calculado."""
        total = self.bias
        weights = self.weights
        for index, value in features.items():
            weight = weights.get(index)
            if weight:
                total += weight * value
        return total

    def predict(self, url: str) -> float:
        """Devuelve ``p`` para una URL, o ``0.0`` si el modelo no está activo."""
        if not self.available:
            return 0.0
        return sigmoid(self.score(url))

    def predict_features(self, features: Mapping[int, float]) -> float:
        """Devuelve ``p`` para un vector hashed ya calculado."""
        if not self.available:
            return 0.0
        return sigmoid(self.score_features(features))

    def threshold(self, name: str) -> float:
        """Devuelve un umbral calibrado, con reserva para artefactos incompletos."""
        default = FALLBACK_THRESHOLDS[0] if name == "medio" else FALLBACK_THRESHOLDS[1]
        value = self.thresholds.get(name)
        return default if value is None else float(value)


def load_model(path: Path = MODEL_PATH) -> LinearModel:
    """Lee y valida el artefacto JSON sin lanzar excepciones al llamador.

    Cualquier fallo de lectura o esquema se degrada a un modelo deshabilitado y
    se registra con el prefijo ``ML_MODEL_INVALID`` para observabilidad.
    """
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
        raw_weights: Any = payload["weights"]
        raw_thresholds: Any = payload["thresholds"]
        weights = {int(index): float(value) for index, value in raw_weights.items()}
        thresholds = {str(name): float(value) for name, value in raw_thresholds.items()}
        if not weights:
            raise ValueError("el artefacto no contiene pesos")
        if "medio" not in thresholds or "alto" not in thresholds:
            raise ValueError("el artefacto no contiene los umbrales medio/alto")
        return LinearModel(
            version=str(payload["version"]),
            feature_spec_version=str(payload["feature_spec_version"]),
            n_features=int(payload["n_features"]),
            bias=float(payload["bias"]),
            weights=weights,
            thresholds=thresholds,
            trained_at=str(payload["trained_at"]),
            data_manifest=dict(payload["data_manifest"]),
            available=True,
        )
    except (OSError, ValueError, TypeError, KeyError) as exc:
        _log.warning("ML_MODEL_INVALID: artefacto no usable (%s)", type(exc).__name__)
        return LinearModel()


@lru_cache(maxsize=1)
def get_model() -> LinearModel:
    """Devuelve la única instancia del modelo del proceso (carga única)."""
    return load_model()


def clear_model_cache() -> None:
    """Fuerza una recarga en la siguiente llamada; útil en pruebas."""
    get_model.cache_clear()


def predict(url: str) -> float:
    """Probabilidad de phishing según el modelo activo (API pública de T10)."""
    return get_model().predict(url)


def model_score(url: str) -> float:
    """Puntuación lineal sin sigmoide; base de la explicabilidad (RF-604)."""
    return get_model().score(url)


__all__ = [
    "FALLBACK_THRESHOLDS",
    "MODEL_GROUPS",
    "MODEL_PATH",
    "LinearModel",
    "clear_model_cache",
    "get_model",
    "load_model",
    "model_score",
    "predict",
    "sigmoid",
]
