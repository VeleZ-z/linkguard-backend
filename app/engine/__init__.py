"""Motor de reglas léxicas de LinkGuard (RF-301).

Expone los modelos internos del pipeline y la matriz de pesos ``wᵢ`` que
alimenta el cálculo del puntaje de riesgo.
"""

from __future__ import annotations

from app.engine.models import ParsedURL, RuleResult
from app.engine.weights import MAX_WEIGHT_SUM, WEIGHTS

__all__ = ["MAX_WEIGHT_SUM", "WEIGHTS", "ParsedURL", "RuleResult"]
