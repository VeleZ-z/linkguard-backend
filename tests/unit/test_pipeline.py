"""Pruebas del registro y del pipeline determinista (H2-T12, H2-T13)."""

from __future__ import annotations

import pytest
from app.engine.models import RuleResult
from app.engine.pipeline import PIPELINE_RULES, run_rules
from app.engine.rules.registry import RULES, Rule
from app.engine.weights import WEIGHTS
from app.normalization import normalize

#: Orden numérico esperado de las 11 reglas.
EXPECTED_RULE_IDS = [
    "F01_EXCESSIVE_LENGTH",
    "F02_DIRECT_IP",
    "F03_MULTIPLE_SUBDOMAINS",
    "F04_SHANNON_ENTROPY",
    "F05_URL_SHORTENER",
    "F06_AT_SYMBOL",
    "F07_HYPHENS_IN_DOMAIN",
    "F08_SCHEMA_REDIRECT",
    "F09_NON_STANDARD_PORT",
    "F10_SPECIAL_CHARS_RATIO",
    "F11_SOCIAL_ENGINEERING_KEYWORDS",
]


class TestRegistry:
    """El registro refleja la matriz de pesos y el catálogo §3."""

    def test_contiene_las_once_reglas_en_orden(self) -> None:
        assert [rule.rule_id for rule in RULES] == EXPECTED_RULE_IDS

    def test_no_hay_identificadores_duplicados(self) -> None:
        assert len({rule.rule_id for rule in RULES}) == len(RULES) == 11

    def test_pesos_alineados_con_weights(self) -> None:
        for rule in RULES:
            clave = rule.rule_id.split("_", 1)[0]
            assert rule.points == WEIGHTS[clave], rule.rule_id

    def test_metadatos_completos(self) -> None:
        for rule in RULES:
            assert isinstance(rule, Rule)
            assert rule.title
            assert rule.description
            assert callable(rule.evaluator)

    def test_pipeline_usa_el_mismo_registro(self) -> None:
        assert list(PIPELINE_RULES) == RULES


class TestRunRules:
    """El pipeline evalúa las 11 reglas sin red ni estado."""

    def test_devuelve_once_resultados_en_orden(self) -> None:
        results = run_rules(normalize("http://example.com/news"))

        assert [result.rule_id for result in results] == EXPECTED_RULE_IDS
        assert all(isinstance(result, RuleResult) for result in results)

    def test_reglas_inactivas_aportan_cero(self) -> None:
        results = run_rules(normalize("http://example.com/news"))

        assert all(result.activated is False for result in results)
        assert all(result.points == 0 for result in results)

    def test_activa_las_reglas_esperadas(self) -> None:
        results = run_rules(normalize("http://10.0.0.1/login"))

        activadas = {result.rule_id for result in results if result.activated}
        assert activadas == {"F02_DIRECT_IP", "F11_SOCIAL_ENGINEERING_KEYWORDS"}

    def test_es_determinista(self) -> None:
        parsed = normalize("http://secure-login.example.com/account/verify")

        assert run_rules(parsed) == run_rules(parsed)

    def test_no_muta_la_url_parseada(self) -> None:
        parsed = normalize("http://example.com/news")
        before = parsed.model_copy(deep=True)

        run_rules(parsed)

        assert parsed == before

    @pytest.mark.parametrize("host", ["10.0.0.1", "example.com"])
    def test_puntos_coinciden_con_pesos_cuando_activa(self, host: str) -> None:
        results = run_rules(normalize(f"http://{host}/"))

        for result in results:
            clave = result.rule_id.split("_", 1)[0]
            esperado = WEIGHTS[clave] if result.activated else 0
            assert result.points == esperado
