"""Exporta el clasificador lineal a ``app/engine/data/model_v1.json`` (RF-602).

El artefacto es JSON plano: sin ``pickle``, ``eval`` ni ``exec`` (RNF-110).
La inferencia en producción es Python puro; las dependencias de entrenamiento
no se importan desde ``app/`` (RF-605).

La poda de pesos casi nulos reduce el tamaño del JSON.  El efecto se mide
sobre la muestra de validación congelada y se reporta en el informe.

Uso::

    .venv/bin/python scripts/ml/export_model.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.metrics import roc_auc_score

ROOT: Path = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ml.features import N_FEATURES  # noqa: E402

DEFAULT_STATE: Path = ROOT / "data" / "processed" / "model_state.json"
DEFAULT_OUTPUT: Path = ROOT / "app" / "engine" / "data" / "model_v1.json"
MAX_BYTES: int = 3 * 1024 * 1024
# 2e-3 reduce el artefacto a ~2.6 MB (límite 3 MB) sin cambiar el AUC de la
# muestra de validación (Δ = 0.0000 en la medición de H5-T09).
DEFAULT_MIN_WEIGHT: float = 2e-3


def sigmoid(value: float) -> float:
    """Sigmoide estable para la inferencia en Python puro."""
    if value >= 0:
        return 1.0 / (1.0 + math.exp(-value))
    exp_value = math.exp(value)
    return exp_value / (1.0 + exp_value)


def pure_predict(features: dict[int, float], bias: float, weights: dict[int, float]) -> float:
    """Inferencia pura ``p = σ(bias + Σ wᵢxᵢ)`` sobre un vector hashed."""
    score = bias
    for index, value in features.items():
        weight = weights.get(index)
        if weight:
            score += weight * value
    return sigmoid(score)


def prune_weights(weights: dict[int, float], min_abs: float) -> dict[int, float]:
    """Elimina pesos cuya magnitud es menor que ``min_abs``."""
    return {index: value for index, value in weights.items() if abs(value) >= min_abs}


def export_model(
    state: dict[str, Any],
    output_path: Path = DEFAULT_OUTPUT,
    min_abs: float = DEFAULT_MIN_WEIGHT,
) -> dict[str, Any]:
    """Escribe el artefacto y devuelve métricas de poda, paridad y tamaño."""
    bias = float(state["bias"])
    full_weights = {int(index): float(value) for index, value in state["weights"].items()}
    thresholds = {key: float(value) for key, value in state["thresholds"].items()}

    sample = state["validation"]["sample"]
    labels = np.array([int(row["label"]) for row in sample])
    features = [{int(k): float(v) for k, v in row["features"].items()} for row in sample]
    reference = np.array([float(row["sklearn_p"]) for row in sample])

    probabilities_full = np.array([pure_predict(vector, bias, full_weights) for vector in features])
    parity = float(np.max(np.abs(probabilities_full - reference)))

    pruned_weights = prune_weights(full_weights, min_abs)
    probabilities_pruned = np.array(
        [pure_predict(vector, bias, pruned_weights) for vector in features]
    )
    auc_full = float(roc_auc_score(labels, probabilities_full))
    auc_pruned = float(roc_auc_score(labels, probabilities_pruned))

    artifact: dict[str, Any] = {
        "version": str(state["version"]),
        "feature_spec_version": str(state["feature_spec_version"]),
        "n_features": int(state["n_features"] or N_FEATURES),
        "bias": bias,
        "weights": {str(index): value for index, value in sorted(pruned_weights.items())},
        "thresholds": thresholds,
        "trained_at": str(state["trained_at"]),
        "data_manifest": state["data_manifest"],
    }
    payload = json.dumps(artifact, separators=(",", ":"), sort_keys=True) + "\n"
    size_bytes = len(payload.encode("utf-8"))
    if size_bytes > MAX_BYTES:
        raise ValueError(
            f"model_v1.json excede el límite de 3 MB ({size_bytes} bytes); "
            "aumentar el umbral de poda"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(payload, encoding="utf-8")

    try:
        reported_path = str(output_path.relative_to(ROOT))
    except ValueError:
        reported_path = str(output_path)
    return {
        "path": reported_path,
        "size_bytes": size_bytes,
        "size_mb": round(size_bytes / (1024 * 1024), 4),
        "sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        "weights_full": len(full_weights),
        "weights_kept": len(pruned_weights),
        "weights_pruned": len(full_weights) - len(pruned_weights),
        "min_abs_weight": min_abs,
        "auc_before_prune": auc_full,
        "auc_after_prune": auc_pruned,
        "auc_delta": auc_pruned - auc_full,
        "max_parity_error": parity,
    }


def main() -> None:
    """CLI para reexportar el artefacto desde el estado guardado."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--min-abs-weight", type=float, default=DEFAULT_MIN_WEIGHT)
    args = parser.parse_args()

    state = json.loads(args.state.read_text(encoding="utf-8"))
    result = export_model(state, args.output, args.min_abs_weight)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
