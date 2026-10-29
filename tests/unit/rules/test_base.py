"""Pruebas de la infraestructura compartida de reglas puras (H2-T01)."""

from __future__ import annotations

from app.engine.models import ParsedURL
from app.engine.rules.base import build_rule_result


def _parsed() -> ParsedURL:
    return ParsedURL(
        scheme="http",
        netloc="example.com",
        host="example.com",
        normalized_url="http://example.com",
    )


class TestBuildRuleResult:
    """Construcción uniforme de ``RuleResult``."""

    def test_activa_conserva_los_puntos(self) -> None:
        result = build_rule_result(
            rule_id="F02_DIRECT_IP",
            points=25,
            activated=True,
            title="Dirección IP directa",
            description="El host es una IP literal.",
        )
        assert result.activated is True
        assert result.points == 25
        assert result.rule_id == "F02_DIRECT_IP"

    def test_inactiva_fuerza_cero_puntos(self) -> None:
        result = build_rule_result(
            rule_id="F02_DIRECT_IP",
            points=25,
            activated=False,
            title="Dirección IP directa",
            description="El host es una IP literal.",
        )
        assert result.activated is False
        assert result.points == 0

    def test_es_determinista(self) -> None:
        kwargs = {
            "rule_id": "F01_EXCESSIVE_LENGTH",
            "points": 10,
            "activated": True,
            "title": "Longitud excesiva de la URL",
            "description": "URL larga.",
        }
        assert build_rule_result(**kwargs) == build_rule_result(**kwargs)

    def test_no_muta_la_entrada(self) -> None:
        parsed = _parsed()
        before = parsed.model_copy(deep=True)
        build_rule_result(
            rule_id="F01_EXCESSIVE_LENGTH",
            points=10,
            activated=True,
            title="Longitud excesiva de la URL",
            description="URL larga.",
        )
        assert parsed == before
