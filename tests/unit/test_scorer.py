"""Pruebas de scoring, clasificación, evidencias y recomendaciones (H2-T14…T16)."""

from __future__ import annotations

import pytest
from app.engine.models import RuleResult
from app.engine.weights import MAX_WEIGHT_SUM, WEIGHTS
from app.schemas import RiskLevel
from app.scoring.evidence import build_evidences, to_evidence
from app.scoring.recommendations import (
    RECOMMENDATION_ALTO,
    RECOMMENDATION_BAJO,
    RECOMMENDATION_MEDIO,
    get_recommendation,
)
from app.scoring.scorer import (
    MAX_SCORE,
    calculate_score,
    classify_risk,
    score_results,
)


def _result(rule_id: str, points: int, *, activated: bool = True) -> RuleResult:
    return RuleResult(
        rule_id=rule_id,
        activated=activated,
        points=points if activated else 0,
        title=f"Título {rule_id}",
        description=f"Descripción {rule_id}",
    )


class TestCalculateScore:
    """Suma ponderada con tope de 100 (RF-301)."""

    def test_tc_rf_301_sin_reglas_activas(self) -> None:
        assert calculate_score([]) == 0

    def test_tc_rf_302_f01_mas_f11(self) -> None:
        results = [_result("F01", 10), _result("F11", 15)]

        assert calculate_score(results) == 25

    def test_tc_rf_303_f02_mas_f08(self) -> None:
        results = [_result("F02", 25), _result("F08", 20)]

        assert calculate_score(results) == 45

    def test_tc_rf_304_f02_f06_f08_f11(self) -> None:
        results = [_result("F02", 25), _result("F06", 20), _result("F08", 20), _result("F11", 15)]

        assert calculate_score(results) == 80

    def test_tc_rf_305_tope_cien(self) -> None:
        results = [_result("X", MAX_WEIGHT_SUM)]

        assert calculate_score(results) == MAX_SCORE == 100

    def test_ignora_reglas_inactivas(self) -> None:
        results = [_result("F02", 25), _result("F08", 20, activated=False)]

        assert calculate_score(results) == 25

    def test_es_estable_ante_el_orden(self) -> None:
        results = [_result("F02", 25), _result("F11", 15)]

        assert calculate_score(results) == calculate_score(reversed(results))


class TestClassifyRisk:
    """Fronteras exactas de RF-302."""

    @pytest.mark.parametrize(
        ("score", "expected"),
        [
            (0, RiskLevel.BAJO),
            (30, RiskLevel.BAJO),
            (31, RiskLevel.MEDIO),
            (69, RiskLevel.MEDIO),
            (70, RiskLevel.ALTO),
            (100, RiskLevel.ALTO),
        ],
    )
    def test_fronteras(self, score: int, expected: RiskLevel) -> None:
        assert classify_risk(score) is expected

    @pytest.mark.parametrize("score", [-1, 101])
    def test_fuera_de_rango(self, score: int) -> None:
        with pytest.raises(ValueError, match="entre 0 y 100"):
            classify_risk(score)

    def test_score_results_combina_ambos_pasos(self) -> None:
        result = score_results([_result("F02", 25), _result("F08", 20)])

        assert result.score == 45
        assert result.risk_level is RiskLevel.MEDIO


class TestEvidence:
    """Desglose granular de RF-303."""

    def test_convierte_solo_reglas_activas(self) -> None:
        results = [
            _result("F02", 25),
            _result("F08", 20, activated=False),
            _result("F11", 15),
        ]

        evidences = build_evidences(results)

        assert [evidence.rule_id for evidence in evidences] == ["F02", "F11"]
        assert [evidence.points for evidence in evidences] == [25, 15]
        assert all(evidence.title and evidence.description for evidence in evidences)

    def test_to_evidence_conserva_metadatos(self) -> None:
        result = _result("F06", 20)

        evidence = to_evidence(result)

        assert evidence.rule_id == result.rule_id
        assert evidence.points == result.points
        assert evidence.title == result.title
        assert evidence.description == result.description


class TestRecommendations:
    """Textos exactos de RF-304."""

    def test_texto_bajo(self) -> None:
        assert RECOMMENDATION_BAJO == (
            "No se detectaron anomalías estructurales severas ni reportes en listas "
            "negras. Mantenga las precauciones habituales al navegar."
        )

    def test_texto_medio(self) -> None:
        assert RECOMMENDATION_MEDIO == (
            "El enlace presenta características inusuales o sospechosas (ej. longitud "
            "elevada, palabras clave o acortadores). Verifique la identidad del "
            "remitente antes de interactuar."
        )

    def test_texto_alto(self) -> None:
        assert RECOMMENDATION_ALTO == (
            "Enlace altamente peligroso o reportado activamente como sospechoso. Se "
            "recomienda NO hacer clic, NO ingresar credenciales ni compartir "
            "información confidencial."
        )

    @pytest.mark.parametrize("level", list(RiskLevel))
    def test_mapea_cada_nivel(self, level: RiskLevel) -> None:
        assert get_recommendation(level)
        assert get_recommendation(level) in {
            RECOMMENDATION_BAJO,
            RECOMMENDATION_MEDIO,
            RECOMMENDATION_ALTO,
        }

    def test_pesos_declarados_suman_mas_de_cien(self) -> None:
        assert WEIGHTS["MATCH_PHISHTANK"] == 50
        assert MAX_WEIGHT_SUM > MAX_SCORE
