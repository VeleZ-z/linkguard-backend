"""Términos de ingeniería social usados por la regla F11 (RF-211).

La colección es inmutable y vive en memoria: no se consulta ninguna fuente
externa durante el análisis (RNF-101).
"""

from __future__ import annotations

from typing import Final

#: Palabras clave asociadas a portales de autenticación y banca en línea.
SENSITIVE_KEYWORDS: Final[frozenset[str]] = frozenset(
    {
        "account",
        "bank",
        "login",
        "secure",
        "service",
        "signin",
        "update",
        "verify",
    }
)

__all__ = ["SENSITIVE_KEYWORDS"]
