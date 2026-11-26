"""Complemento de ``test_scoring_v3.py`` para el scorer normativo v3 (H5-T14).

Cubre combinaciones de precedencia no incluidas en la suite original, el cap
de 30 de la allowlist, el piso Medio del feed por host, la invariante de puntos
con calibration por tramos, el reparto RF-704 con contribuciones desiguales y
la conservación estricta del comportamiento v2 cuando no hay señales v3.
"""

from __future__ import annotations

from typing import Final

import pytest
from app.engine.models import RuleResult
from app.ml.model import MODEL_GROUPS
from app.schemas import RiskLevel
from app.scoring.calibration import get_thresholds
from app.scoring.evidence import build_evidences
from app.scoring.scorer import calculate_score, score_results, score_v3

#: Puntos y grupos ML que aparecen cuando el modelo domina a las reglas.
ML_GRUPOS_TOP3: Final[tuple[str, ...]] = ("ML_TLD_RISK", "ML_DOMAIN_SHAPE", "ML_HOST_PATTERN")

#: Casos de precedencia FU > A > FH > modelo/reglas con sus evidencias esperadas.
CASOS_PRECEDENCIA: Final[
    tuple[tuple[str, dict[str, bool | int], int, RiskLevel, tuple[str, ...]], ...]
] = (
    (
        "allowlist_cap",
        {"allowlisted": True, "s_ml": 90},
        30,
        RiskLevel.BAJO,
        ("F02", *ML_GRUPOS_TOP3, "TRUSTED_DOMAIN"),
    ),
    (
        "allowlist_ignora_feed_host",
        {"allowlisted": True, "feed_host": True, "s_ml": 90},
        30,
        RiskLevel.BAJO,
        ("F02", *ML_GRUPOS_TOP3, "TRUSTED_DOMAIN"),
    ),
    (
        "abusable_ignora_allowlist_y_feed_host",
        {"allowlisted": True, "abusable": True, "feed_host": True, "s_ml": 90},
        90,
        RiskLevel.ALTO,
        ("F02", *ML_GRUPOS_TOP3),
    ),
    (
        "feed_url_gana_a_phishtank",
        {"feed_url": True, "phishtank_match": True, "s_ml": 90},
        100,
        RiskLevel.ALTO,
        ("F02", *ML_GRUPOS_TOP3, "MATCH_FEED_URL"),
    ),
    (
        "feed_host_y_unverified_se_suman",
        {"feed_host": True, "phishtank_unverified": True, "s_ml": 0},
        65,
        RiskLevel.MEDIO,
        ("F02", "PHISHTANK_UNVERIFIED", "MATCH_FEED_HOST"),
    ),
    (
        "allowlist_con_unverified",
        {"allowlisted": True, "phishtank_unverified": True, "s_ml": 90},
        45,
        RiskLevel.MEDIO,
        ("F02", *ML_GRUPOS_TOP3, "TRUSTED_DOMAIN", "PHISHTANK_UNVERIFIED"),
    ),
    (
        "abusable_con_feed_url",
        {"allowlisted": True, "abusable": True, "feed_url": True, "s_ml": 90},
        100,
        RiskLevel.ALTO,
        ("F02", *ML_GRUPOS_TOP3, "MATCH_FEED_URL"),
    ),
)


def _resultado(rule_id: str, points: int) -> RuleResult:
    """Construye un resultado de regla activo con metadatos mínimos."""
    return RuleResult(
        rule_id=rule_id,
        activated=True,
        points=points,
        title=f"Título {rule_id}",
        description=f"Descripción {rule_id}",
    )


def _reglas(puntos: tuple[tuple[str, int], ...]) -> list[RuleResult]:
    """Construye resultados activos a partir de pares (id, puntos)."""
    return [_resultado(rule_id, valor) for rule_id, valor in puntos]


class TestPrecedenciaCombinada:
    """La precedencia y las evidencias coinciden con el algoritmo normativo §5."""

    @pytest.mark.parametrize(
        ("nombre", "opciones", "puntaje", "nivel", "reglas_evidencia"),
        CASOS_PRECEDENCIA,
        ids=[caso[0] for caso in CASOS_PRECEDENCIA],
    )
    def test_precedencia_y_evidencias(
        self,
        nombre: str,
        opciones: dict[str, bool | int],
        puntaje: int,
        nivel: RiskLevel,
        reglas_evidencia: tuple[str, ...],
    ) -> None:
        """Puntaje, nivel y orden de evidencias son deterministas."""
        resultados = _reglas((("F02", 10),))
        desglose = score_v3(resultados, **opciones)
        evidencias = build_evidences(resultados, **opciones)

        assert desglose.score == puntaje
        assert desglose.risk_level is nivel
        assert tuple(evidence.rule_id for evidence in evidencias) == reglas_evidencia

    @pytest.mark.parametrize(
        ("puntos_reglas", "s_ml"),
        [(45, 10), (10, 90)],
        ids=["reglas_dominan", "modelo_domina"],
    )
    def test_cap_30_de_la_allowlist(self, puntos_reglas: int, s_ml: int) -> None:
        """El cap limita el score a 30 sin alterar las evidencias de ``S_pre``."""
        resultados = _reglas((("F02", puntos_reglas),))
        desglose = score_v3(resultados, s_ml=s_ml, allowlisted=True)
        evidencias = build_evidences(resultados, s_ml=s_ml, allowlisted=True)

        assert desglose.s_pre == max(puntos_reglas, s_ml)
        assert desglose.score == min(desglose.s_pre, 30) == 30
        assert desglose.risk_level is RiskLevel.BAJO
        assert desglose.trusted is True
        assert sum(evidence.points for evidence in evidencias) == desglose.s_pre

    @pytest.mark.parametrize(
        ("puntos_reglas", "s_ml"),
        [(0, 0), (10, 0), (0, 20)],
        ids=["sin_señales", "solo_reglas", "solo_modelo"],
    )
    def test_piso_medio_con_feed_host(self, puntos_reglas: int, s_ml: int) -> None:
        """Un host en el feed nunca deja la clasificación por debajo de Medio."""
        resultados = _reglas((("F02", puntos_reglas),))
        desglose = score_v3(resultados, s_ml=s_ml, feed_host=True)

        assert desglose.feed_host is True
        assert desglose.score == min(100, max(puntos_reglas, s_ml) + 40)
        assert desglose.score >= 31
        assert desglose.risk_level is RiskLevel.MEDIO


class TestInvarianteDePuntos:
    """Σ puntos de evidencias = ``S_pre`` salvo los topes documentados."""

    def test_invariante_con_calibracion_por_tramos(self) -> None:
        """``p`` produce las mismas evidencias que su ``s_ml`` calibrado."""
        resultados = _reglas((("F02", 10),))
        t_medio, t_alto = get_thresholds()
        muestras: tuple[tuple[float, int], ...] = (
            (0.0, 0),
            (t_medio, 31),
            (t_alto, 70),
            (1.0, 100),
        )

        for probabilidad, s_ml_esperado in muestras:
            desglose = score_v3(resultados, p=probabilidad)
            evidencias = build_evidences(resultados, p=probabilidad)

            assert desglose.s_ml == s_ml_esperado
            assert desglose.s_pre == max(10, s_ml_esperado)
            assert sum(evidence.points for evidence in evidencias) == desglose.s_pre
            assert desglose.score == desglose.s_pre

    def test_tope_de_cien_con_reglas_y_modelo_saturados(self) -> None:
        """Con ``s_ml`` fuera de rango, las evidencias conservan los puntos v2."""
        resultados = _reglas((("X", 120),))
        desglose = score_v3(resultados, s_ml=150)
        evidencias = build_evidences(resultados, s_ml=150)

        assert desglose.s_rules == 100
        assert desglose.s_ml == desglose.s_pre == desglose.score == 100
        # Excepción documentada en ``test_scoring_v3.py``: la regla individual
        # conserva sus 120 puntos aunque el score agregado se acote a 100.
        assert sum(evidence.points for evidence in evidencias) == 120

    def test_modelo_no_aporta_si_las_reglas_dominan(self) -> None:
        """Con ``S_ml < S_rules`` no se generan evidencias ML (RF-704)."""
        resultados = _reglas((("F11", 15), ("F08", 20), ("F01", 10)))
        desglose = score_v3(resultados, s_ml=30)
        evidencias = build_evidences(resultados, s_ml=30)

        assert desglose.s_pre == 45
        assert desglose.ml_delta == -15
        assert desglose.ml_points == {}
        assert not [e for e in evidencias if e.rule_id in MODEL_GROUPS]
        assert sum(e.points for e in evidencias) == desglose.score == 45

    def test_s_ml_explicito_prevalece_sobre_p(self) -> None:
        """La señal ``s_ml`` inyectada gana sobre la probabilidad ``p``."""
        resultados = _reglas((("F02", 10),))

        desglose = score_v3(resultados, s_ml=70, p=0.0)
        evidencias = build_evidences(resultados, s_ml=70, p=0.0)

        assert desglose.s_ml == 70
        assert desglose.score == 70
        assert sum(e.points for e in evidencias) == 70


class TestRepartoRF704:
    """El reparto por mayor resto es proporcional y determinista."""

    def test_contribuciones_desiguales_y_mayor_resto(self) -> None:
        """Los tres grupos con más contribución reciben todo el delta."""
        resultados = _reglas((("F01", 10),))
        contribuciones: dict[str, float] = {
            "ML_BRAND_MISMATCH": 0.5,
            "ML_PATH_PATTERN": 0.25,
            "ML_TLD_RISK": 0.25,
        }

        desglose = score_v3(resultados, s_ml=20, ml_contributions=contribuciones)
        evidencias = build_evidences(resultados, s_ml=20, ml_contributions=contribuciones)
        puntos_ml = {e.rule_id: e.points for e in evidencias if e.rule_id in MODEL_GROUPS}

        assert desglose.ml_delta == 10
        # El empate entre PATH y TLD se decide por el orden del catálogo §6.
        assert desglose.ml_points == {
            "ML_BRAND_MISMATCH": 5,
            "ML_TLD_RISK": 3,
            "ML_PATH_PATTERN": 2,
        }
        assert puntos_ml == desglose.ml_points
        assert sum(puntos_ml.values()) == 10
        assert sum(e.points for e in evidencias) == desglose.score == 20


class TestCompatibilidadV2:
    """``calculate_score`` y ``score_results`` ignoran señales v3 ausentes."""

    @pytest.mark.parametrize(
        ("match", "unverified", "puntaje", "nivel"),
        [
            (False, False, 45, RiskLevel.MEDIO),
            (True, False, 95, RiskLevel.ALTO),
            (False, True, 60, RiskLevel.MEDIO),
        ],
        ids=["sin_reputacion", "match", "unverified"],
    )
    def test_score_v2_con_reputacion_phishtank(
        self, match: bool, unverified: bool, puntaje: int, nivel: RiskLevel
    ) -> None:
        """La reputación v2 se mantiene intacta sin inyectar señales v3."""
        resultados = _reglas((("F02", 25), ("F08", 20)))

        assert (
            calculate_score(resultados, phishtank_match=match, phishtank_unverified=unverified)
            == puntaje
        )
        calculo = score_results(resultados, phishtank_match=match, phishtank_unverified=unverified)
        assert calculo.score == puntaje
        assert calculo.risk_level is nivel
        assert (
            sum(
                e.points
                for e in build_evidences(
                    resultados, phishtank_match=match, phishtank_unverified=unverified
                )
            )
            == puntaje
        )
