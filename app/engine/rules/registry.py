"""Registro determinista de las 11 reglas léxicas puras (RF-301).

Cada entrada :class:`Rule` expone el identificador, el peso ``wᵢ``, el título
y la descripción que publica el contrato, junto con la función pura de
evaluación. El orden del registro es el orden numérico F01…F11, de modo que
las evidencias y los puntajes sean reproducibles entre ejecuciones.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from app.engine.models import ParsedURL, RuleResult
from app.engine.rules import (
    f01_excessive_length,
    f02_direct_ip,
    f03_multiple_subdomains,
    f04_shannon_entropy,
    f05_url_shortener,
    f06_at_symbol,
    f07_hyphens_in_domain,
    f08_schema_redirect,
    f09_non_standard_port,
    f10_special_chars_ratio,
    f11_social_engineering_keywords,
)
from app.engine.rules.base import RuleEvaluator


@dataclass(frozen=True, slots=True)
class Rule:
    """Metadatos y función pura de una regla léxica."""

    rule_id: str
    points: int
    title: str
    description: str
    evaluator: RuleEvaluator

    def evaluate(self, parsed_url: ParsedURL) -> RuleResult:
        """Ejecuta la función pura asociada sobre una URL normalizada."""
        return self.evaluator(parsed_url)


#: Las 11 reglas en orden numérico estable F01…F11.
RULES: Final[list[Rule]] = [
    Rule(
        f01_excessive_length.RULE_ID,
        f01_excessive_length.POINTS,
        f01_excessive_length.TITLE,
        f01_excessive_length.DESCRIPTION,
        f01_excessive_length.evaluate_excessive_length,
    ),
    Rule(
        f02_direct_ip.RULE_ID,
        f02_direct_ip.POINTS,
        f02_direct_ip.TITLE,
        f02_direct_ip.DESCRIPTION,
        f02_direct_ip.evaluate_direct_ip,
    ),
    Rule(
        f03_multiple_subdomains.RULE_ID,
        f03_multiple_subdomains.POINTS,
        f03_multiple_subdomains.TITLE,
        f03_multiple_subdomains.DESCRIPTION,
        f03_multiple_subdomains.evaluate_multiple_subdomains,
    ),
    Rule(
        f04_shannon_entropy.RULE_ID,
        f04_shannon_entropy.POINTS,
        f04_shannon_entropy.TITLE,
        f04_shannon_entropy.DESCRIPTION,
        f04_shannon_entropy.evaluate_shannon_entropy,
    ),
    Rule(
        f05_url_shortener.RULE_ID,
        f05_url_shortener.POINTS,
        f05_url_shortener.TITLE,
        f05_url_shortener.DESCRIPTION,
        f05_url_shortener.evaluate_url_shortener,
    ),
    Rule(
        f06_at_symbol.RULE_ID,
        f06_at_symbol.POINTS,
        f06_at_symbol.TITLE,
        f06_at_symbol.DESCRIPTION,
        f06_at_symbol.evaluate_at_symbol,
    ),
    Rule(
        f07_hyphens_in_domain.RULE_ID,
        f07_hyphens_in_domain.POINTS,
        f07_hyphens_in_domain.TITLE,
        f07_hyphens_in_domain.DESCRIPTION,
        f07_hyphens_in_domain.evaluate_hyphens_in_domain,
    ),
    Rule(
        f08_schema_redirect.RULE_ID,
        f08_schema_redirect.POINTS,
        f08_schema_redirect.TITLE,
        f08_schema_redirect.DESCRIPTION,
        f08_schema_redirect.evaluate_schema_redirect,
    ),
    Rule(
        f09_non_standard_port.RULE_ID,
        f09_non_standard_port.POINTS,
        f09_non_standard_port.TITLE,
        f09_non_standard_port.DESCRIPTION,
        f09_non_standard_port.evaluate_non_standard_port,
    ),
    Rule(
        f10_special_chars_ratio.RULE_ID,
        f10_special_chars_ratio.POINTS,
        f10_special_chars_ratio.TITLE,
        f10_special_chars_ratio.DESCRIPTION,
        f10_special_chars_ratio.evaluate_special_chars_ratio,
    ),
    Rule(
        f11_social_engineering_keywords.RULE_ID,
        f11_social_engineering_keywords.POINTS,
        f11_social_engineering_keywords.TITLE,
        f11_social_engineering_keywords.DESCRIPTION,
        f11_social_engineering_keywords.evaluate_social_engineering_keywords,
    ),
]

__all__ = ["RULES", "Rule"]
