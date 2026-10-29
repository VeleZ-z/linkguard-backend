"""Pruebas unitarias de modelos internos y matriz de pesos (RF-301).

Verifica la instanciación y atributos de ``ParsedURL`` y ``RuleResult``, y
la coincidencia exacta de la matriz de pesos ``wᵢ`` en
``app.engine.weights`` con el contrato §3 de la especificación.
"""

from __future__ import annotations

import pytest
from app.engine.models import ParsedURL, RuleResult
from app.engine.weights import MAX_WEIGHT_SUM, WEIGHTS
from pydantic import ValidationError

# --- Pesos esperados según el contrato §3 ----------------------------------

EXPECTED_WEIGHTS: dict[str, int] = {
    "MATCH_PHISHTANK": 50,
    "F02": 25,
    "F06": 20,
    "F08": 20,
    "F11": 15,
    "F05": 15,
    "F04": 15,
    "F09": 10,
    "F03": 10,
    "F01": 10,
    "F07": 8,
    "F10": 7,
}


class TestParsedURL:
    """Validación del modelo interno ParsedURL (RF-103)."""

    def test_instanciacion_completa(self) -> None:
        parsed = ParsedURL(
            scheme="https",
            netloc="subdomain.example.com:8443",
            host="subdomain.example.com",
            port=8443,
            path="/login-path",
            params=";session=1",
            query="q=1&lang=es",
            fragment="section",
            normalized_url=(
                "https://subdomain.example.com:8443/login-path;session=1?q=1&lang=es#section"
            ),
        )
        assert parsed.scheme == "https"
        assert parsed.netloc == "subdomain.example.com:8443"
        assert parsed.host == "subdomain.example.com"
        assert parsed.port == 8443
        assert parsed.path == "/login-path"
        assert parsed.params == ";session=1"
        assert parsed.query == "q=1&lang=es"
        assert parsed.fragment == "section"
        assert "normalized_url" in parsed.model_dump()

    def test_puerto_opcional_por_defecto(self) -> None:
        parsed = ParsedURL(
            scheme="http",
            netloc="example.com",
            host="example.com",
            path="/",
            normalized_url="http://example.com/",
        )
        assert parsed.port is None

    def test_campos_vacios_por_defecto(self) -> None:
        parsed = ParsedURL(
            scheme="http",
            netloc="example.com",
            host="example.com",
            normalized_url="http://example.com",
        )
        assert parsed.path == ""
        assert parsed.params == ""
        assert parsed.query == ""
        assert parsed.fragment == ""

    def test_serializacion_json(self) -> None:
        parsed = ParsedURL(
            scheme="http",
            netloc="example.com",
            host="example.com",
            normalized_url="http://example.com",
        )
        data = parsed.model_dump(mode="json")
        assert data["scheme"] == "http"
        assert data["netloc"] == "example.com"
        assert data["host"] == "example.com"
        assert data["normalized_url"] == "http://example.com"


class TestRuleResult:
    """Validación del modelo interno RuleResult."""

    def test_instanciacion_regla_activada(self) -> None:
        result = RuleResult(
            rule_id="F02_DIRECT_IP",
            activated=True,
            points=25,
            title="Dirección IP directa",
            description="El host es una dirección IP directa.",
        )
        assert result.rule_id == "F02_DIRECT_IP"
        assert result.activated is True
        assert result.points == 25
        assert result.title == "Dirección IP directa"
        assert "dirección ip" in result.description.lower()

    def test_instanciacion_regla_no_activada(self) -> None:
        result = RuleResult(
            rule_id="F01_EXCESSIVE_LENGTH",
            activated=False,
            points=0,
            title="Longitud excesiva",
            description="La URL no supera el umbral de 75 caracteres.",
        )
        assert result.activated is False
        assert result.points == 0

    def test_puntos_no_negativos(self) -> None:
        """Los puntos de una regla no pueden ser negativos."""
        with pytest.raises(ValidationError):
            RuleResult(
                rule_id="F01",
                activated=True,
                points=-5,
                title="x",
                description="desc",
            )

    def test_serializacion_json(self) -> None:
        result = RuleResult(
            rule_id="F06_AT_SYMBOL",
            activated=True,
            points=20,
            title="Símbolo '@' en URL",
            description="Se detectó el carácter '@' en la estructura de la URL.",
        )
        data = result.model_dump(mode="json")
        assert data["rule_id"] == "F06_AT_SYMBOL"
        assert data["activated"] is True
        assert data["points"] == 20


class TestWeightsMatrix:
    """Validación de la matriz de pesos wᵢ (contrato §3)."""

    def test_matriz_exacta(self) -> None:
        """La matriz cargada debe coincidir exactamente con el contrato §3."""
        assert WEIGHTS == EXPECTED_WEIGHTS

    def test_todos_los_pesos_positivos(self) -> None:
        for rule_id, weight in WEIGHTS.items():
            assert weight > 0, f"Peso de {rule_id} no es positivo"

    def test_cantidad_de_reglas(self) -> None:
        """Son 12 entradas: MATCH_PHISHTANK + F01..F11."""
        assert len(WEIGHTS) == 12

    def test_claves_esperadas(self) -> None:
        assert set(WEIGHTS) == set(EXPECTED_WEIGHTS)

    def test_suma_maxima_teorica(self) -> None:
        """La suma teórica de todos los pesos supera el tope de 100."""
        assert MAX_WEIGHT_SUM == sum(EXPECTED_WEIGHTS.values())
        assert MAX_WEIGHT_SUM > 100  # Se acota a 100 en el scoring

    def test_pesos_por_regla(self) -> None:
        """Cada peso coincide con el valor documentado en el contrato §3."""
        assert WEIGHTS["MATCH_PHISHTANK"] == 50
        assert WEIGHTS["F02"] == 25
        assert WEIGHTS["F06"] == 20
        assert WEIGHTS["F08"] == 20
        assert WEIGHTS["F11"] == 15
        assert WEIGHTS["F05"] == 15
        assert WEIGHTS["F04"] == 15
        assert WEIGHTS["F09"] == 10
        assert WEIGHTS["F03"] == 10
        assert WEIGHTS["F01"] == 10
        assert WEIGHTS["F07"] == 8
        assert WEIGHTS["F10"] == 7
