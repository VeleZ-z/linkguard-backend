"""F11 — Palabras clave sensibles (RF-211).

Regla pura: busca términos de ingeniería social en host, path y query sin
distinguir mayúsculas/minúsculas. La lista vive en
``app/engine/data/sensitive_keywords.py``.
"""

from __future__ import annotations

from typing import Final

from app.engine.data.sensitive_keywords import SENSITIVE_KEYWORDS
from app.engine.models import ParsedURL, RuleResult
from app.engine.rules.base import build_rule_result
from app.engine.weights import WEIGHTS

RULE_ID: Final[str] = "F11_SOCIAL_ENGINEERING_KEYWORDS"
POINTS: Final[int] = WEIGHTS["F11"]

TITLE: Final[str] = "Palabras clave sensibles"
DESCRIPTION: Final[str] = (
    "La URL contiene términos asociados a portales de acceso, banca o "
    "verificación de cuentas, usados habitualmente para suplantar servicios."
)


def evaluate_social_engineering_keywords(parsed_url: ParsedURL) -> RuleResult:
    """Activa F11 ante palabras clave sensibles en host/path/query (RF-211).

    Args:
        parsed_url: URL normalizada por el módulo de normalización.

    Returns:
        ``RuleResult`` con ``points=15`` si se activa y ``0`` si no.
    """
    haystack = f"{parsed_url.host} {parsed_url.path} {parsed_url.query}".lower()
    activated = any(keyword in haystack for keyword in SENSITIVE_KEYWORDS)
    return build_rule_result(
        rule_id=RULE_ID,
        points=POINTS,
        activated=activated,
        title=TITLE,
        description=DESCRIPTION,
    )


__all__ = [
    "DESCRIPTION",
    "POINTS",
    "RULE_ID",
    "TITLE",
    "evaluate_social_engineering_keywords",
]
