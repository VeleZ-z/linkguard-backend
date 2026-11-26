"""Pruebas del algoritmo de scoring v3 y sus evidencias (H5-T11).

Verifica el desglose normativo del adendo §5 (``S_pre = max(S_rules, S_ml)``,
reparto de ``S_ml - S_rules`` por mayor resto, allowlist, feeds y reputación),
la invariante Σ puntos = ``S_pre`` (RF-704), las fronteras de riesgo, la
calibración lineal por tramos (RF-702), los umbrales por entorno (RF-603) y la
compatibilidad con las expectativas v2 (RF-301…303).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Final

import pytest
from app.core.config import get_settings
from app.engine.models import RuleResult
from app.schemas import RiskLevel
from app.scoring.calibration import PUNTOS_NUDOS, get_thresholds, piecewise_linear
from app.scoring.evidence import ML_EVIDENCE_TEXTS, build_evidences, ml_evidence
from app.scoring.scorer import (
    calculate_score,
    classify_risk,
    distribute_ml_points,
    score_results,
    score_v3,
)

#: Títulos del catálogo de evidencias del adendo §6 (RF-704).
TITULOS_CATALOGO: Final[dict[str, str]] = {
    "ML_TLD_RISK": "Extensión de dominio frecuente en phishing",
    "ML_DOMAIN_SHAPE": "Nombre de dominio aleatorio o atípico",
    "ML_HOST_PATTERN": "Patrones sospechosos en el nombre del host",
    "ML_PATH_PATTERN": "Ruta con patrones típicos de phishing",
    "ML_BRAND_MISMATCH": "Marca conocida en un dominio que no es el oficial",
    "ML_URL_SHAPE": "Estructura general inusual",
}

_CONTRIBUCIONES: Final[dict[str, float]] = {
    "ML_TLD_RISK": 0.6,
    "ML_DOMAIN_SHAPE": 0.3,
    "ML_HOST_PATTERN": 0.1,
}
_REGLAS_45: Final[tuple[tuple[str, int], ...]] = (("F11", 15), ("F08", 20), ("F01", 10))


def _result(rule_id: str, points: int) -> RuleResult:
    """Construye un resultado de regla activado con metadatos mínimos."""
    return RuleResult(
        rule_id=rule_id,
        activated=True,
        points=points,
        title=f"Título {rule_id}",
        description=f"Descripción {rule_id}",
    )


def _reglas(puntos: tuple[tuple[str, int], ...] = ()) -> list[RuleResult]:
    """Construye una lista de resultados activos a partir de pares (id, puntos)."""
    return [_result(rule_id, points) for rule_id, points in puntos]


@pytest.fixture
def umbrales_entorno_limpios(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Aísla los umbrales por entorno y limpia la caché de ``get_settings``."""
    get_settings.cache_clear()
    yield
    # ``monkeypatch`` restaura el entorno original al finalizar; hay que
    # limpiar la variable aquí para no cachear el valor de prueba.
    monkeypatch.delenv("MODEL_THRESHOLD_MEDIO", raising=False)
    monkeypatch.delenv("MODEL_THRESHOLD_ALTO", raising=False)
    get_settings.cache_clear()


class TestDesgloseRF704:
    """TC-RF-704-01: S_ml=60 y S_rules=15 dejan 45 puntos que repartir."""

    def test_tc_rf_704_01_desglose_del_score(self) -> None:
        desglose = score_v3(
            [_result("F01", 10), _result("F11", 5)],
            s_ml=60,
            ml_contributions=_CONTRIBUCIONES,
        )

        assert desglose.score == 60
        assert desglose.risk_level is RiskLevel.MEDIO
        assert desglose.s_rules == 15
        assert desglose.s_ml == 60
        assert desglose.s_pre == 60
        assert desglose.ml_delta == 45
        assert sum(desglose.ml_points.values()) == 45
        assert len(desglose.ml_points) <= 3
        assert all(puntos >= 1 for puntos in desglose.ml_points.values())

    def test_tc_rf_704_01_evidencias_y_catalogo_del_adendo(self) -> None:
        resultados = [_result("F01", 10), _result("F11", 5)]
        desglose = score_v3(resultados, s_ml=60, ml_contributions=_CONTRIBUCIONES)
        evidencias = build_evidences(resultados, s_ml=60, ml_contributions=_CONTRIBUCIONES)

        ml_evidencias = [e for e in evidencias if e.rule_id in ML_EVIDENCE_TEXTS]
        assert sum(e.points for e in ml_evidencias) == 45
        assert len(ml_evidencias) <= 3
        assert sum(e.points for e in evidencias) == desglose.s_pre == 60
        assert all(e.title and e.description for e in ml_evidencias)
        assert set(ML_EVIDENCE_TEXTS) == set(TITULOS_CATALOGO)

        for rule_id, (titulo, descripcion) in ML_EVIDENCE_TEXTS.items():
            # Los textos son los publicados en el catálogo es-419 del adendo §6.
            assert titulo == TITULOS_CATALOGO[rule_id]
            assert descripcion and isinstance(descripcion, str)
            evidencia = ml_evidence(rule_id, 1)
            assert evidencia.rule_id == rule_id
            assert evidencia.title == titulo
            assert evidencia.description == descripcion


class TestInvariantePuntos:
    """La suma de puntos de las evidencias debe ser ``S_pre`` sin reputación."""

    @pytest.mark.parametrize(
        ("puntos_reglas", "s_ml"),
        [(0, 20), (15, 60), (45, 45), (80, 10), (25, 90)],
        ids=["ml_domina", "delta_45", "empate", "reglas_dominan", "ml_alto"],
    )
    def test_suma_evidencias_igual_s_pre(self, puntos_reglas: int, s_ml: int) -> None:
        resultados = _reglas((("F02", puntos_reglas),))
        desglose = score_v3(resultados, s_ml=s_ml)
        evidencias = build_evidences(resultados, s_ml=s_ml)

        # Sin reputación y con S_pre < 100 no hay tope que rompa la invariante.
        assert desglose.s_pre < 100
        assert sum(e.points for e in evidencias) == desglose.s_pre

    def test_excepcion_del_tope_de_cien_en_las_reglas(self) -> None:
        resultados = _reglas((("X", 60), ("Y", 60)))
        desglose = score_v3(resultados, s_ml=20)
        evidencias = build_evidences(resultados, s_ml=20)

        # S_rules se acota a 100 en el scorer, pero las evidencias individuales
        # conservan sus puntos: la igualdad solo se exige con S_pre < 100.
        assert desglose.s_rules == desglose.s_pre == 100
        assert sum(e.points for e in evidencias) == 120


class TestRepartoMayorResto:
    """El reparto es determinista, usa como máximo tres grupos y no da ceros."""

    def test_empate_se_resuelve_por_el_orden_del_catalogo(self) -> None:
        # Seis grupos empatados, declarados en orden inverso al catálogo.
        empatadas = dict.fromkeys(
            (
                "ML_URL_SHAPE",
                "ML_BRAND_MISMATCH",
                "ML_PATH_PATTERN",
                "ML_HOST_PATTERN",
                "ML_DOMAIN_SHAPE",
                "ML_TLD_RISK",
            ),
            1.0,
        )

        reparto = distribute_ml_points(10, empatadas)

        # El desempate sigue el orden del adendo §6: TLD, dominio y host.
        assert reparto == {
            "ML_TLD_RISK": 4,
            "ML_DOMAIN_SHAPE": 3,
            "ML_HOST_PATTERN": 3,
        }
        assert sum(reparto.values()) == 10

    def test_cinco_grupos_positivos_se_reducen_a_tres(self) -> None:
        contribuciones = {
            "ML_TLD_RISK": 5.0,
            "ML_DOMAIN_SHAPE": 4.0,
            "ML_HOST_PATTERN": 3.0,
            "ML_PATH_PATTERN": 2.0,
            "ML_BRAND_MISMATCH": 1.0,
        }

        reparto = distribute_ml_points(10, contribuciones)

        assert len(reparto) <= 3
        assert set(reparto) <= set(contribuciones)
        assert sum(reparto.values()) == 10
        assert all(puntos >= 1 for puntos in reparto.values())

    def test_resultado_no_depende_del_orden_del_diccionario(self) -> None:
        contribuciones = {
            "ML_TLD_RISK": 1.0,
            "ML_HOST_PATTERN": 1.0,
            "ML_PATH_PATTERN": 1.0,
            "ML_URL_SHAPE": 1.0,
            "ML_DOMAIN_SHAPE": 1.0,
        }

        normal = distribute_ml_points(10, contribuciones)
        invertido = distribute_ml_points(10, dict(reversed(list(contribuciones.items()))))

        assert normal == invertido
        assert sum(normal.values()) == 10

    @pytest.mark.parametrize("delta", [0, -5], ids=["cero", "negativo"])
    def test_delta_no_positivo_no_genera_evidencias_ml(self, delta: int) -> None:
        assert distribute_ml_points(delta, _CONTRIBUCIONES) == {}


class TestAllowlistRF705:
    """TC-RF-705-01: allowlist limita a 30 salvo señales de coincidencia exacta."""

    def test_tc_rf_705_01_cap_y_evidencia_informativa(self) -> None:
        resultados = _reglas(_REGLAS_45)
        desglose = score_v3(resultados, allowlisted=True)
        evidencias = build_evidences(resultados, allowlisted=True)

        assert desglose.score <= 30
        assert desglose.score == 30
        assert desglose.risk_level is RiskLevel.BAJO
        assert desglose.trusted is True
        trusted = [e for e in evidencias if e.rule_id == "TRUSTED_DOMAIN"]
        assert len(trusted) == 1
        assert trusted[0].points == 0
        assert trusted[0].title and trusted[0].description

    def test_abusable_rompe_el_cap(self) -> None:
        resultados = _reglas(_REGLAS_45)

        desglose = score_v3(resultados, allowlisted=True, abusable=True)

        assert desglose.trusted is False
        assert desglose.score == 45
        assert desglose.risk_level is RiskLevel.MEDIO
        assert all(
            e.rule_id != "TRUSTED_DOMAIN"
            for e in build_evidences(resultados, allowlisted=True, abusable=True)
        )

    def test_feed_url_rompe_el_cap(self) -> None:
        resultados = _reglas(_REGLAS_45)
        desglose = score_v3(resultados, allowlisted=True, feed_url=True)

        assert desglose.trusted is False
        assert desglose.score == 95
        assert desglose.risk_level is RiskLevel.ALTO

    def test_phishtank_match_rompe_el_cap(self) -> None:
        resultados = _reglas(_REGLAS_45)
        desglose = score_v3(resultados, allowlisted=True, phishtank_match=True)

        assert desglose.trusted is False
        assert desglose.score == 95
        assert desglose.risk_level is RiskLevel.ALTO


class TestFeedsLocales:
    """RF-803/RF-804: precedencia FU > A > FH > modelo/reglas."""

    def test_feed_url_suma_cincuenta_y_fuerza_alto(self) -> None:
        desglose = score_v3([], feed_url=True)
        evidencias = build_evidences([], feed_url=True)

        assert desglose.score == 50
        assert desglose.risk_level is RiskLevel.ALTO
        assert desglose.feed_url is True
        assert [(e.rule_id, e.points) for e in evidencias] == [("MATCH_FEED_URL", 50)]
        assert evidencias[0].title and evidencias[0].description

    def test_feed_host_suma_cuarenta_y_fija_piso_medio(self) -> None:
        desglose = score_v3([], feed_host=True)
        evidencias = build_evidences([], feed_host=True)

        assert desglose.score == 40
        assert desglose.risk_level is RiskLevel.MEDIO
        assert desglose.feed_host is True
        assert [(e.rule_id, e.points) for e in evidencias] == [("MATCH_FEED_HOST", 40)]

    def test_feed_host_con_reglas_bajas_no_baja_de_medio(self) -> None:
        desglose = score_v3([_result("F01", 10)], feed_host=True)

        assert desglose.score == 50
        assert desglose.risk_level is RiskLevel.MEDIO

    def test_feed_host_se_ignora_con_allowlist(self) -> None:
        desglose = score_v3([], feed_host=True, allowlisted=True)
        evidencias = build_evidences([], feed_host=True, allowlisted=True)

        assert desglose.score == 0
        assert desglose.feed_host is False
        assert desglose.trusted is True
        assert [e.rule_id for e in evidencias] == ["TRUSTED_DOMAIN"]
        assert all(e.points == 0 for e in evidencias)

    def test_phishtank_unverified_suma_quince_sin_forzar_alto(self) -> None:
        desglose = score_v3([], phishtank_unverified=True)
        evidencias = build_evidences([], phishtank_unverified=True)

        assert desglose.score == 15
        assert desglose.risk_level is RiskLevel.BAJO
        assert desglose.phishtank_unverified is True
        assert [(e.rule_id, e.points) for e in evidencias] == [("PHISHTANK_UNVERIFIED", 15)]

    def test_coincidencia_exacta_tiene_prioridad_sobre_unverified(self) -> None:
        desglose = score_v3([], phishtank_match=True, phishtank_unverified=True)
        evidencias = build_evidences([], phishtank_match=True, phishtank_unverified=True)

        assert desglose.score == 50
        assert desglose.risk_level is RiskLevel.ALTO
        assert desglose.phishtank_match is True
        assert desglose.phishtank_unverified is False
        assert [e.rule_id for e in evidencias] == ["MATCH_PHISHTANK"]


class TestFronterasYCalibracionRF702:
    """Fronteras inclusivas 30/31 y 69/70; nudos de la PL (0,0)…(1,100)."""

    @pytest.mark.parametrize(
        ("puntos", "nivel"),
        [
            (30, RiskLevel.BAJO),
            (31, RiskLevel.MEDIO),
            (69, RiskLevel.MEDIO),
            (70, RiskLevel.ALTO),
        ],
    )
    def test_clasifica_en_las_fronteras(self, puntos: int, nivel: RiskLevel) -> None:
        assert classify_risk(puntos) is nivel

    @pytest.mark.parametrize(
        ("probabilidad", "puntos"),
        [(0.0, 0), ("medio", 31), ("alto", 70), (1.0, 100)],
        ids=["cero", "t_medio", "t_alto", "uno"],
    )
    def test_nudos_de_la_lineal_por_tramos(self, probabilidad: float | str, puntos: int) -> None:
        t_medio, t_alto = get_thresholds()
        valores: dict[str, float] = {"medio": t_medio, "alto": t_alto}
        p = valores[probabilidad] if isinstance(probabilidad, str) else probabilidad

        assert PUNTOS_NUDOS == (0, 31, 70, 100)
        assert piecewise_linear(p) == puntos


class TestUmbralesPorEntornoRF603:
    """Los umbrales pueden sobrescribirse con variables de entorno."""

    def test_sobrescribe_t_medio_desde_el_entorno(
        self, monkeypatch: pytest.MonkeyPatch, umbrales_entorno_limpios: None
    ) -> None:
        monkeypatch.setenv("MODEL_THRESHOLD_MEDIO", "0.4")
        get_settings.cache_clear()

        assert get_thresholds()[0] == 0.4
        assert piecewise_linear(0.4) == 31

    def test_variable_vacia_equivale_a_sin_sobrescritura(
        self, monkeypatch: pytest.MonkeyPatch, umbrales_entorno_limpios: None
    ) -> None:
        monkeypatch.setenv("MODEL_THRESHOLD_MEDIO", "")
        get_settings.cache_clear()

        assert get_settings().MODEL_THRESHOLD_MEDIO is None
        assert get_thresholds()[0] > 0.0


class TestCompatibilidadV2:
    """Humo de RF-301/RF-303: las expectativas v2 no se modifican."""

    def test_score_y_nivel_v2_siguen_igual(self) -> None:
        resultados = [_result("F02", 25), _result("F08", 20)]

        assert calculate_score(resultados) == 45
        assert score_results(resultados).risk_level is RiskLevel.MEDIO
