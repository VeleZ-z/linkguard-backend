"""Pruebas de integración del analizador v3 con reputación local (H5-T12).

El scoring v3 está protegido por ``ENABLE_V3_SCORING``: la fixture ``v3_activo``
lo habilita de forma aislada. PhishTank se sustituye siempre por un doble que no
abre sockets (regla de mocks obligatorios) y ``get_reputation`` se parchea con
señales controladas para no depender de los artefactos binarios reales.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Final

import httpx
import pytest
from app.clients.phishtank import PhishtankResult
from app.core.config import get_settings
from app.engine.pipeline import run_rules
from app.main import app
from app.ml import predict
from app.normalization import normalize
from app.reputation import ReputationSignals
from app.schemas import PhishtankStatus
from app.scoring.calibration import piecewise_linear
from app.scoring.scorer import score_v3

API_PATH: Final[str] = "/api/v1/analyze"
SNAPSHOT: Final[Path] = Path(__file__).resolve().parents[1].joinpath("data/openapi_snapshot.json")

#: URL léxicamente limpia; el riesgo observado proviene del clasificador local.
URL_SIN_SEÑALES: Final[str] = "http://example.com/news"
#: Dominio no allowlisteado con probabilidad ML alta y reglas léxicas vacías.
URL_CON_FEED: Final[str] = "https://phish-example.invalid/novedades"

CLAVES_CONTRATO: Final[frozenset[str]] = frozenset(
    {
        "url_analyzed",
        "normalized_url",
        "score",
        "risk_level",
        "recommendation",
        "evidences",
        "phishtank_status",
        "execution_time_ms",
    }
)


@pytest.fixture
def v3_activo(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Activa el scoring v3 y limpia la caché de ajustes al finalizar."""

    monkeypatch.setenv("ENABLE_V3_SCORING", "true")
    get_settings.cache_clear()
    yield
    # ``monkeypatch`` ya restauró la variable: hay que descartar el objeto
    # cacheado para no filtrar el valor de prueba a otras suites.
    get_settings.cache_clear()


class _ClienteFalso:
    """Doble de PhishTank que devuelve un resultado prefijado sin red."""

    def __init__(
        self,
        *,
        status: PhishtankStatus = PhishtankStatus.UNAVAILABLE,
        is_match: bool = False,
        is_unverified: bool = False,
    ) -> None:
        self._resultado = PhishtankResult(
            is_match=is_match,
            is_unverified=is_unverified,
            status=status,
        )

    async def check_url(self, url: str) -> PhishtankResult:
        """Ignora la URL de entrada y entrega el resultado configurado."""

        return self._resultado


def _inyectar_dobles(
    monkeypatch: pytest.MonkeyPatch,
    señales: ReputationSignals | None = None,
    cliente: _ClienteFalso | None = None,
) -> None:
    """Sustituye reputación local y cliente externo por dobles deterministas."""

    señales_efectivas = señales if señales is not None else ReputationSignals()
    cliente_efectivo = cliente if cliente is not None else _ClienteFalso()
    monkeypatch.setattr("app.services.analyzer.get_reputation", lambda _parsed: señales_efectivas)
    monkeypatch.setattr("app.services.analyzer.get_phishtank_client", lambda: cliente_efectivo)


def _score_local(url: str) -> int:
    """Score v3 sin reputación, calculado con los componentes reales."""

    parsed = normalize(url)
    reglas = run_rules(parsed)
    return score_v3(reglas, s_ml=piecewise_linear(predict(parsed.normalized_url))).score


async def _analizar(client: httpx.AsyncClient, url: str) -> dict[str, Any]:
    """Invoca el endpoint congelado y exige HTTP 200."""

    response = await client.post(API_PATH, json={"url": url})
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    return body


def _evidencias(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Indexa las evidencias por ``rule_id`` para facilitar las aserciones."""

    return {evidencia["rule_id"]: evidencia for evidencia in body["evidences"]}


class TestContratoCongelado:
    """El esquema HTTP y sus claves no cambian con el scoring v3."""

    def test_openapi_sin_cambios(self) -> None:
        """Aserción estricta: diff vacío frente al snapshot anterior a T12/T13."""

        assert app.openapi() == json.loads(SNAPSHOT.read_text(encoding="utf-8"))

    async def test_contrato_congelado(
        self,
        client: httpx.AsyncClient,
        v3_activo: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """La respuesta conserva exactamente las ocho claves del contrato."""

        _inyectar_dobles(monkeypatch)
        body = await _analizar(client, URL_SIN_SEÑALES)

        assert set(body) == CLAVES_CONTRATO


class TestFeedsLocales:
    """RF-803/RF-804: precedencia FU > A > FH > modelo/reglas."""

    async def test_tc_rf_804_01_feed_host_y_allowlist(
        self,
        client: httpx.AsyncClient,
        v3_activo: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Un host en el feed suma 40; la allowlist y RF-503 lo neutralizan."""

        _inyectar_dobles(monkeypatch, ReputationSignals(feed_host=True))
        body = await _analizar(client, URL_CON_FEED)

        assert body["score"] >= 40
        assert body["risk_level"] in {"Medio", "Alto"}
        assert body["score"] == min(100, _score_local(URL_CON_FEED) + 40)
        assert _evidencias(body)["MATCH_FEED_HOST"]["points"] == 40

        _inyectar_dobles(monkeypatch, ReputationSignals(feed_host=True, allowlisted=True))
        permitido = await _analizar(client, URL_CON_FEED)
        evidencias = _evidencias(permitido)

        assert permitido["score"] <= 30
        assert permitido["score"] == min(30, _score_local(URL_CON_FEED))
        assert "MATCH_FEED_HOST" not in evidencias
        assert evidencias["TRUSTED_DOMAIN"]["points"] == 0

        _inyectar_dobles(monkeypatch, ReputationSignals(feed_host=True, abusable=True))
        abusable = await _analizar(client, URL_CON_FEED)

        assert "MATCH_FEED_HOST" not in _evidencias(abusable)
        assert abusable["score"] == _score_local(URL_CON_FEED)

    async def test_allowlist_cap_y_precedencia(
        self,
        client: httpx.AsyncClient,
        v3_activo: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """La allowlist limita a 30 y deja una evidencia informativa de 0 puntos."""

        _inyectar_dobles(monkeypatch, ReputationSignals(allowlisted=True))
        body = await _analizar(client, URL_CON_FEED)

        assert body["score"] <= 30
        assert body["score"] == min(30, _score_local(URL_CON_FEED))
        assert body["risk_level"] == "Bajo"
        evidencias = _evidencias(body)
        assert "TRUSTED_DOMAIN" in evidencias
        assert evidencias["TRUSTED_DOMAIN"]["points"] == 0

    @pytest.mark.parametrize(
        ("cliente", "señales", "regla"),
        [
            (
                _ClienteFalso(is_match=True, status=PhishtankStatus.AVAILABLE),
                ReputationSignals(allowlisted=True),
                "MATCH_PHISHTANK",
            ),
            (
                _ClienteFalso(),
                ReputationSignals(allowlisted=True, feed_url=True),
                "MATCH_FEED_URL",
            ),
        ],
        ids=["phishtank_match", "feed_url"],
    )
    async def test_coincidencia_exacta_rompe_el_cap(
        self,
        client: httpx.AsyncClient,
        v3_activo: None,
        monkeypatch: pytest.MonkeyPatch,
        cliente: _ClienteFalso,
        señales: ReputationSignals,
        regla: str,
    ) -> None:
        """Una coincidencia exacta confirmada anula el cap de la allowlist."""

        _inyectar_dobles(monkeypatch, señales, cliente)
        body = await _analizar(client, URL_CON_FEED)
        evidencias = _evidencias(body)

        assert body["score"] > 30
        # La coincidencia exacta anula el cap: el bono de +50 se aplica a S_pre.
        assert body["score"] == min(100, _score_local(URL_CON_FEED) + 50)
        assert body["risk_level"] == "Alto"
        assert regla in evidencias
        assert "TRUSTED_DOMAIN" not in evidencias


class TestResilienciaV3:
    """Los fallos externos y de componentes nunca producen HTTP 500."""

    @pytest.mark.parametrize(
        ("status", "valor"),
        [
            (PhishtankStatus.TIMEOUT, "timeout"),
            (PhishtankStatus.UNAVAILABLE, "unavailable"),
        ],
        ids=["timeout", "503"],
    )
    async def test_timeout_y_503_siguen_siendo_200(
        self,
        client: httpx.AsyncClient,
        v3_activo: None,
        monkeypatch: pytest.MonkeyPatch,
        status: PhishtankStatus,
        valor: str,
    ) -> None:
        """Timeout y 503 entregan el puntaje local con su estado real."""

        _inyectar_dobles(monkeypatch, cliente=_ClienteFalso(status=status))
        body = await _analizar(client, URL_SIN_SEÑALES)
        ids = set(_evidencias(body))

        assert body["phishtank_status"] == valor
        assert body["score"] == _score_local(URL_SIN_SEÑALES)
        assert isinstance(body["score"], int)
        assert 0 <= body["score"] <= 100
        assert "MATCH_PHISHTANK" not in ids
        assert "PHISHTANK_UNVERIFIED" not in ids

    @pytest.mark.parametrize("componente", ["predict", "contributions_by_group", "get_reputation"])
    async def test_degradacion_por_componente(
        self,
        client: httpx.AsyncClient,
        v3_activo: None,
        monkeypatch: pytest.MonkeyPatch,
        componente: str,
    ) -> None:
        """Cada señal local falla por separado sin tumbar la respuesta."""

        _inyectar_dobles(monkeypatch)

        def _falla(*_args: object, **_kwargs: object) -> None:
            raise RuntimeError(f"fallo simulado en {componente}")

        monkeypatch.setattr(f"app.services.analyzer.{componente}", _falla)
        body = await _analizar(client, URL_CON_FEED)
        ids = set(_evidencias(body))

        assert isinstance(body["score"], int)
        assert 0 <= body["score"] <= 100
        if componente == "predict":
            # Sin probabilidad no hay delta ML que repartir en evidencias.
            assert not any(rule_id.startswith("ML_") for rule_id in ids)
        else:
            assert any(rule_id.startswith("ML_") for rule_id in ids)


class TestInvariantePuntos:
    """Σ puntos de evidencias = score cuando no hay cap de 100 ni reputación."""

    async def test_invariante_points_v3(
        self,
        client: httpx.AsyncClient,
        v3_activo: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """El desglose expuesto cuadra con el score y usa textos en español."""

        _inyectar_dobles(monkeypatch)
        body = await _analizar(client, URL_SIN_SEÑALES)

        # Excepción documentada: con S_pre = 100 el scorer acota el score pero
        # las evidencias conservan sus puntos individuales (ver test_scoring_v3).
        assert 0 <= body["score"] < 100
        assert sum(e["points"] for e in body["evidences"]) == body["score"]
        assert all(e["title"] and e["description"] for e in body["evidences"])
