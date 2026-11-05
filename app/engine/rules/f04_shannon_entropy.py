"""F04 — Entropía de Shannon adaptativa del host (RF-204).

Regla pura: evalúa la aleatoriedad **por etiqueta** en lugar de sobre el host
completo, de modo que un subdominio generado por un DGA no quede diluido por
el dominio registrable legítimo que lo acompaña. Sin red ni estado.

Estrategia (OBS de precisión sobre RF-204):

1. Si el host es una IP literal, la regla no evalúa: F02 ya la penaliza.
2. Se separan las etiquetas de subdominio del dominio registrable con la
   *Public Suffix List* (``publicsuffix2``).
3. Si hay subdominios, se calcula ``H(X)`` sobre **cada** etiqueta de longitud
   ``>= 6`` y se activa si alguna supera 4.5 bits/símbolo.
4. Si no hay subdominios, se calcula ``H(X)`` sobre el nombre del dominio
   registrable (sin el sufijo público).

El umbral se mantiene en 4.5 para preservar la comparabilidad con la
especificación y con los resultados históricos.
"""

from __future__ import annotations

import ipaddress
import math
from collections import Counter
from typing import Final

from publicsuffix2 import get_sld

from app.engine.models import ParsedURL, RuleResult
from app.engine.rules.base import build_rule_result
from app.engine.weights import WEIGHTS

RULE_ID: Final[str] = "F04_SHANNON_ENTROPY"
POINTS: Final[int] = WEIGHTS["F04"]

#: Umbral estricto de entropía que activa la regla (bits por símbolo).
MAX_ENTROPY: Final[float] = 4.5

#: Longitud mínima de una etiqueta para que su entropía sea significativa.
#: Las etiquetas cortas (``a``, ``www``, ``api``) no distinguen un DGA de un
#: nombre legítimo y solo aportarían ruido.
MIN_LABEL_LENGTH: Final[int] = 6

TITLE: Final[str] = "Entropía de Shannon alta"
DESCRIPTION: Final[str] = (
    "El host contiene una etiqueta con aleatoriedad alta (H > 4.5), un patrón "
    "típico de dominios generados automáticamente por algoritmos DGA."
)


def shannon_entropy(value: str) -> float:
    """Calcula la entropía de Shannon de una cadena en bits por símbolo."""
    if not value:
        return 0.0
    total = len(value)
    return -sum((count / total) * math.log2(count / total) for count in Counter(value).values())


def _is_ip_literal(parsed_url: ParsedURL) -> bool:
    """Determina si el host es una IP, aunque el modelo no lo marque."""
    if parsed_url.is_ip:
        return True
    candidate = parsed_url.host.strip().strip("[]")
    if not candidate:
        return False
    try:
        ipaddress.ip_address(candidate)
    except ValueError:
        return False
    return True


def _split_registrable(host: str) -> tuple[list[str], str]:
    """Separa las etiquetas de subdominio del dominio registrable (eTLD+1)."""
    normalized = host.strip().rstrip(".").lower()
    if not normalized:
        return [], ""
    try:
        main_domain = get_sld(normalized) or normalized
    except (TypeError, ValueError):  # pragma: no cover - defensa ante PSL inválida
        main_domain = normalized
    if normalized == main_domain:
        return [], main_domain
    labels = normalized.split(".")
    subdomains = labels[: -len(main_domain.split("."))]
    return subdomains, main_domain


def _candidate_labels(parsed_url: ParsedURL) -> list[str]:
    """Devuelve las etiquetas sobre las que corresponde medir la entropía.

    Se prefieren los campos ya calculados por el normalizador (``subdomains``
    y ``main_domain``) y se recurre a la *Public Suffix List* cuando el
    ``ParsedURL`` se construyó manualmente.
    """
    if parsed_url.subdomains:
        return list(parsed_url.subdomains)
    if parsed_url.main_domain is not None:
        return [parsed_url.main_domain.split(".")[0]] if parsed_url.main_domain else []
    subdomains, main_domain = _split_registrable(parsed_url.host)
    if subdomains:
        return subdomains
    return [main_domain.split(".")[0]] if main_domain else []


def evaluate_shannon_entropy(parsed_url: ParsedURL) -> RuleResult:
    """Activa F04 cuando alguna etiqueta relevante supera 4.5 (RF-204).

    Args:
        parsed_url: URL normalizada por el módulo de normalización.

    Returns:
        ``RuleResult`` con ``points=15`` si se activa y ``0`` si no. Los hosts
        que son IP literal nunca activan la regla (las gestiona F02).
    """
    activated = False
    if not _is_ip_literal(parsed_url):
        labels = (
            label for label in _candidate_labels(parsed_url) if len(label) >= MIN_LABEL_LENGTH
        )
        activated = any(shannon_entropy(label) > MAX_ENTROPY for label in labels)

    return build_rule_result(
        rule_id=RULE_ID,
        points=POINTS,
        activated=activated,
        title=TITLE,
        description=DESCRIPTION,
    )


__all__ = [
    "DESCRIPTION",
    "MAX_ENTROPY",
    "MIN_LABEL_LENGTH",
    "POINTS",
    "RULE_ID",
    "TITLE",
    "evaluate_shannon_entropy",
    "shannon_entropy",
]
