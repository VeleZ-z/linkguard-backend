"""F11 — Palabras clave sensibles multilingües (RF-211).

Regla pura: busca términos de ingeniería social en host, path y query. Antes
de comparar, la URL se normaliza con ``unicodedata`` (NFKD), se descartan los
diacríticos y se pasa a minúsculas, de modo que ``contraseña`` y
``CONTRASENA`` coinciden con el término canónico ``contrasena``.

La comparación es **consciente de tokens** para elevar la precisión frente a
la búsqueda de subcadenas: un término corto y ambiguo (``pin``, ``rut``,
``dian``…) solo coincide como palabra completa, mientras que los términos
largos admiten prefijo/sufijo (``password`` en ``passwords``) y las formas
compuestas admiten separadores (``iniciar-sesion``, ``iniciar sesion`` o
``iniciar_sesion``). El catálogo vive en
``app/engine/data/sensitive_keywords.py``.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from typing import Final

from app.engine.data.sensitive_keywords import EXACT_MATCH_KEYWORDS, SENSITIVE_KEYWORDS
from app.engine.models import ParsedURL, RuleResult
from app.engine.rules.base import build_rule_result
from app.engine.weights import WEIGHTS

RULE_ID: Final[str] = "F11_SOCIAL_ENGINEERING_KEYWORDS"
POINTS: Final[int] = WEIGHTS["F11"]

TITLE: Final[str] = "Palabras clave sensibles"
DESCRIPTION: Final[str] = (
    "La URL contiene términos asociados a portales de acceso, banca, "
    "verificación de cuentas o datos personales, usados habitualmente para "
    "suplantar servicios."
)

_TOKEN_RE: Final[re.Pattern[str]] = re.compile(r"[a-z0-9]+")

#: Longitud mínima para aceptar coincidencias por prefijo o sufijo dentro de
#: un token. Los términos más cortos solo coinciden como token completo,
#: salvo que estén en ``EXACT_MATCH_KEYWORDS`` (que se excluyen de afijos).
_MIN_AFFIX_LENGTH: Final[int] = 4


def normalize_text(value: str) -> str:
    """Descompone, elimina diacríticos y pasa a minúsculas (NFKD + ASCII)."""
    decomposed = unicodedata.normalize("NFKD", value)
    return decomposed.encode("ascii", "ignore").decode("ascii").lower()


def tokenize(value: str) -> list[str]:
    """Divide el texto normalizado en tokens alfanuméricos."""
    return _TOKEN_RE.findall(normalize_text(value))


def _matches_token_sequence(compact_keyword: str, tokens: Sequence[str]) -> bool:
    """Busca una forma compuesta en ventanas de tokens contiguos.

    Permite que ``iniciar-sesion`` coincida con ``iniciar sesion``,
    ``iniciar_sesion`` o ``iniciar%20sesion`` (ya decodificado por el
    normalizador), sin unir tokens que no son adyacentes.
    """
    limit = len(compact_keyword)
    for start in range(len(tokens)):
        accumulated = ""
        for token in tokens[start:]:
            accumulated += token
            if len(accumulated) > limit:
                break
            if accumulated == compact_keyword:
                return True
    return False


def matches_keyword(keyword: str, tokens: Sequence[str]) -> bool:
    """Determina si un término del catálogo aparece en la secuencia de tokens.

    Args:
        keyword: Término canónico (minúsculas, sin diacríticos, con guiones).
        tokens: Tokens alfanuméricos de la URL normalizada.

    Returns:
        ``True`` si el término coincide como token completo, como prefijo o
        sufijo de un token (términos de cuatro o más caracteres) o como forma
        compuesta en tokens contiguos.
    """
    compact = keyword.replace("-", "")
    if not compact:
        return False

    exact_only = keyword in EXACT_MATCH_KEYWORDS or compact in EXACT_MATCH_KEYWORDS
    for token in tokens:
        if token == compact:
            return True
        if (
            not exact_only
            and len(compact) >= _MIN_AFFIX_LENGTH
            and (token.startswith(compact) or token.endswith(compact))
        ):
            return True

    return "-" in keyword and _matches_token_sequence(compact, tokens)


def evaluate_social_engineering_keywords(parsed_url: ParsedURL) -> RuleResult:
    """Activa F11 ante palabras clave sensibles en host/path/query (RF-211).

    Args:
        parsed_url: URL normalizada por el módulo de normalización.

    Returns:
        ``RuleResult`` con ``points=15`` si se activa y ``0`` si no.
    """
    haystack_fields = (parsed_url.host, parsed_url.path, parsed_url.query)
    tokens_by_field = [tokenize(field) for field in haystack_fields]
    activated = any(
        matches_keyword(keyword, tokens)
        for tokens in tokens_by_field
        for keyword in SENSITIVE_KEYWORDS
    )
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
    "matches_keyword",
    "normalize_text",
    "tokenize",
]
