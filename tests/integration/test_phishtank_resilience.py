"""Pruebas de integración de resiliencia contra PhishTank con mocks estrictos (H3-T08).

Cada prueba intercepta ``PHISHTANK_API_URL`` con ``respx``: **prohibido tráfico
real saliente**. Cubre TC-RF-401, TC-RF-402, TC-RF-403 y TC-RF-404.
"""

from __future__ import annotations

import httpx
import pytest
import respx
from app.cache.phishtank_cache import reset_phishtank_cache
from app.clients.phishtank import get_phishtank_client, reset_phishtank_client
from app.core.config import get_settings

API_URL = get_settings().PHISHTANK_API_URL

#: URLs de prueba con distinto perfil léxico.
URL_LIMPIA = "http://example.com/news"
URL_SOSPECHOSA = "http://10.0.0.1/login"


def _payload_encontrado() -> dict:
    return {"results": {"in_database": True, "valid": True}}


def _payload_no_encontrado() -> dict:
    return {"results": {"in_database": False, "valid": True}}


def _cliente_real(monkeypatch: pytest.MonkeyPatch) -> None:
    """Restaura el cliente real para que respx intercepte su httpx."""
    reset_phishtank_cache()
    reset_phishtank_client()
    monkeypatch.setattr("app.services.analyzer.get_phishtank_client", get_phishtank_client)


class TestTCRF401TCRF402:
    """Reputación disponible: match (+50, Alto) y no match (solo léxico)."""

    @respx.mock
    async def test_tc_rf_401_url_enlista_negra(
        self, client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ruta = respx.post(API_URL).mock(
            return_value=httpx.Response(200, json=_payload_encontrado())
        )
        _cliente_real(monkeypatch)

        response = await client.post("/api/v1/analyze", json={"url": URL_LIMPIA})

        assert response.status_code == 200
        body = response.json()
        assert body["phishtank_status"] == "available"
        assert body["score"] == 50
        assert body["risk_level"] == "Alto"
        assert "MATCH_PHISHTANK" in {e["rule_id"] for e in body["evidences"]}
        assert ruta.called

    @respx.mock
    async def test_tc_rf_402_url_no_encontrada(
        self, client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        respx.post(API_URL).mock(return_value=httpx.Response(200, json=_payload_no_encontrado()))
        _cliente_real(monkeypatch)

        response = await client.post("/api/v1/analyze", json={"url": URL_SOSPECHOSA})

        assert response.status_code == 200
        body = response.json()
        assert body["phishtank_status"] == "available"
        assert body["score"] == 40
        assert body["risk_level"] == "Medio"
        assert "MATCH_PHISHTANK" not in {e["rule_id"] for e in body["evidences"]}


class TestTCRF403:
    """Timeout de PhishTank (> 4.0 s): HTTP 200 con status="timeout"."""

    @respx.mock
    async def test_tc_rf_403_timeout_retorna_200(
        self, client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        respx.post(API_URL).mock(side_effect=httpx.ReadTimeout("tiempo agotado"))
        _cliente_real(monkeypatch)

        response = await client.post("/api/v1/analyze", json={"url": URL_SOSPECHOSA})

        assert response.status_code == 200
        body = response.json()
        assert body["phishtank_status"] == "timeout"
        assert body["score"] == 40
        assert body["risk_level"] == "Medio"
        assert "MATCH_PHISHTANK" not in {e["rule_id"] for e in body["evidences"]}


class TestTCRF404:
    """Error de red / HTTP 503: HTTP 200 con status="unavailable"."""

    @respx.mock
    async def test_tc_rf_404_http_503_retorna_200(
        self, client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        respx.post(API_URL).mock(return_value=httpx.Response(503))
        _cliente_real(monkeypatch)

        response = await client.post("/api/v1/analyze", json={"url": URL_LIMPIA})

        assert response.status_code == 200
        body = response.json()
        assert body["phishtank_status"] == "unavailable"
        assert body["score"] == 0
        assert body["risk_level"] == "Bajo"


class TestCachéEndpoint:
    """Segunda consulta de la misma URL recupera desde caché (status="cached")."""

    @respx.mock
    async def test_segunda_consulta_desde_cache(
        self, client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ruta = respx.post(API_URL).mock(
            return_value=httpx.Response(200, json=_payload_encontrado())
        )
        _cliente_real(monkeypatch)

        primera = await client.post("/api/v1/analyze", json={"url": URL_LIMPIA})
        segunda = await client.post("/api/v1/analyze", json={"url": URL_LIMPIA})

        assert primera.json()["phishtank_status"] == "available"
        assert segunda.json()["phishtank_status"] == "cached"
        assert segunda.json()["risk_level"] == "Alto"
        # respx vio una sola petición HTTP real.
        assert ruta.call_count == 1
