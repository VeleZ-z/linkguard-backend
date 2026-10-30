"""Pruebas del orquestador concurrente (H3-T05, RF-401, RF-405).

Se inyecta un cliente de reputación falso: ninguna prueba abre sockets ni
contacta PhishTank (RNF-101).
"""

from __future__ import annotations

from app.clients.phishtank import PhishtankResult
from app.schemas import PhishtankStatus, RiskLevel
from app.services.analyzer import analyze_url

URL_LIMPIA = "http://example.com/news"
URL_SOSPECHOSA = "http://10.0.0.1/login"


class _ClienteFalso:
    """Doble de prueba que registra las URLs consultadas."""

    def __init__(self, result: PhishtankResult) -> None:
        self._result = result
        self.urls: list[str] = []

    async def check_url(self, url: str) -> PhishtankResult:
        self.urls.append(url)
        return self._result


class _ClienteQueFalla:
    """Cliente que incumple el contrato y lanza una excepción inesperada."""

    async def check_url(self, url: str) -> PhishtankResult:
        raise RuntimeError("fallo inesperado")


class TestAnalyzeUrlReputacion:
    """Consolidación de score, evidencias y estado externo."""

    async def test_match_suma_cincuenta_y_fuerza_alto(self) -> None:
        cliente = _ClienteFalso(PhishtankResult(is_match=True, status=PhishtankStatus.AVAILABLE))

        response = await analyze_url(URL_LIMPIA, client=cliente)

        assert response.score == 50
        assert response.risk_level is RiskLevel.ALTO
        assert response.phishtank_status is PhishtankStatus.AVAILABLE
        assert [evidence.rule_id for evidence in response.evidences] == ["MATCH_PHISHTANK"]

    async def test_sin_match_conserva_el_analisis_lexico(self) -> None:
        cliente = _ClienteFalso(PhishtankResult(is_match=False, status=PhishtankStatus.AVAILABLE))

        response = await analyze_url(URL_SOSPECHOSA, client=cliente)

        assert response.score == 40
        assert response.risk_level is RiskLevel.MEDIO
        assert "MATCH_PHISHTANK" not in {e.rule_id for e in response.evidences}

    async def test_timeout_no_altera_el_analisis_local(self) -> None:
        cliente = _ClienteFalso(PhishtankResult(is_match=False, status=PhishtankStatus.TIMEOUT))

        response = await analyze_url(URL_SOSPECHOSA, client=cliente)

        assert response.phishtank_status is PhishtankStatus.TIMEOUT
        assert response.score == 40
        assert response.risk_level is RiskLevel.MEDIO

    async def test_unavailable_no_altera_el_analisis_local(self) -> None:
        cliente = _ClienteFalso(PhishtankResult(is_match=False, status=PhishtankStatus.UNAVAILABLE))

        response = await analyze_url(URL_LIMPIA, client=cliente)

        assert response.phishtank_status is PhishtankStatus.UNAVAILABLE
        assert response.score == 0
        assert response.risk_level is RiskLevel.BAJO

    async def test_cached_se_propaga_a_la_respuesta(self) -> None:
        cliente = _ClienteFalso(PhishtankResult(is_match=True, status=PhishtankStatus.CACHED))

        response = await analyze_url(URL_LIMPIA, client=cliente)

        assert response.phishtank_status is PhishtankStatus.CACHED
        assert response.risk_level is RiskLevel.ALTO


class TestAnalyzeUrlContrato:
    """Campos del contrato §6 calculados por el orquestador."""

    async def test_consulta_la_url_normalizada(self) -> None:
        cliente = _ClienteFalso(PhishtankResult(status=PhishtankStatus.AVAILABLE))

        response = await analyze_url("  EXAMPLE.com/news  ", client=cliente)

        assert cliente.urls == [response.normalized_url]
        assert response.url_analyzed == "  EXAMPLE.com/news  "

    async def test_mide_el_tiempo_total(self) -> None:
        cliente = _ClienteFalso(PhishtankResult(status=PhishtankStatus.AVAILABLE))

        response = await analyze_url(URL_LIMPIA, client=cliente)

        assert response.execution_time_ms >= 0.0

    async def test_recomendacion_acorde_al_nivel_forzado(self) -> None:
        cliente = _ClienteFalso(PhishtankResult(is_match=True, status=PhishtankStatus.AVAILABLE))

        response = await analyze_url(URL_LIMPIA, client=cliente)

        assert "NO hacer clic" in response.recommendation

    async def test_fallo_inesperado_del_cliente_degrada_a_unavailable(self) -> None:
        response = await analyze_url(URL_LIMPIA, client=_ClienteQueFalla())

        assert response.phishtank_status is PhishtankStatus.UNAVAILABLE
        assert response.score == 0
        assert response.risk_level is RiskLevel.BAJO
