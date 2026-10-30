"""Pruebas de integración de la capa HTTP (base de H1-T13).

Usan ``httpx.ASGITransport``: no se abre ningún socket real. Cubren el
contrato §6, los manejadores de error, CORS y el aislamiento de trazas.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from app.clients.phishtank import PhishtankResult
from app.core.rate_limit import limiter
from app.main import app
from app.schemas import PhishtankStatus

VALID_URL = "http://example.com/news"


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> None:
    """Evita que el contador de slowapi se filtre entre pruebas."""
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    """Cliente ASGI sin red real."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client


class TestHealth:
    """/health responde la identidad del servicio."""

    async def test_health_200(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "healthy"
        assert body["service"] == "linkguard-api"
        assert body["version"] == "1.0.0"
        assert "timestamp" in body


RECOMENDACION_BAJO = (
    "No se detectaron anomalías estructurales severas ni reportes en listas "
    "negras. Mantenga las precauciones habituales al navegar."
)
RECOMENDACION_MEDIO = (
    "El enlace presenta características inusuales o sospechosas (ej. longitud "
    "elevada, palabras clave o acortadores). Verifique la identidad del "
    "remitente antes de interactuar."
)
RECOMENDACION_ALTO = (
    "Enlace altamente peligroso o reportado activamente como sospechoso. Se "
    "recomienda NO hacer clic, NO ingresar credenciales ni compartir "
    "información confidencial."
)


class TestAnalyzeContrato:
    """POST /api/v1/analyze devuelve el contrato §6 con scoring real."""

    async def test_url_sin_anomalias(self, client: httpx.AsyncClient) -> None:
        response = await client.post("/api/v1/analyze", json={"url": VALID_URL})
        assert response.status_code == 200
        body = response.json()
        assert body["url_analyzed"] == VALID_URL
        assert body["normalized_url"] == VALID_URL
        assert body["score"] == 0
        assert body["risk_level"] == "Bajo"
        assert body["evidences"] == []
        assert body["phishtank_status"] == "unavailable"
        assert body["execution_time_ms"] >= 0
        assert body["recommendation"] == RECOMENDACION_BAJO

    async def test_url_riesgo_medio(self, client: httpx.AsyncClient) -> None:
        response = await client.post("/api/v1/analyze", json={"url": "http://10.0.0.1/login"})
        assert response.status_code == 200
        body = response.json()
        assert body["score"] == 40
        assert body["risk_level"] == "Medio"
        assert body["recommendation"] == RECOMENDACION_MEDIO
        assert {e["rule_id"] for e in body["evidences"]} == {
            "F02_DIRECT_IP",
            "F11_SOCIAL_ENGINEERING_KEYWORDS",
        }

    async def test_url_riesgo_alto(self, client: httpx.AsyncClient) -> None:
        response = await client.post(
            "/api/v1/analyze",
            json={"url": "http://user@10.0.0.1/login?next=https://evil.example"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["score"] == 80
        assert body["risk_level"] == "Alto"
        assert body["recommendation"] == RECOMENDACION_ALTO
        assert [e["rule_id"] for e in body["evidences"]] == [
            "F02_DIRECT_IP",
            "F06_AT_SYMBOL",
            "F08_SCHEMA_REDIRECT",
            "F11_SOCIAL_ENGINEERING_KEYWORDS",
        ]
        assert sum(e["points"] for e in body["evidences"]) == body["score"]

    async def test_evidencias_coherentes_con_score(self, client: httpx.AsyncClient) -> None:
        response = await client.post(
            "/api/v1/analyze", json={"url": "http://a.b.c.example.com:8080/"}
        )
        body = response.json()
        assert body["score"] == sum(e["points"] for e in body["evidences"])
        for evidence in body["evidences"]:
            assert evidence["title"]
            assert evidence["description"]

    async def test_normaliza_url_sin_esquema(self, client: httpx.AsyncClient) -> None:
        response = await client.post("/api/v1/analyze", json={"url": "example.com/login-path"})
        assert response.status_code == 200
        body = response.json()
        assert body["url_analyzed"] == "example.com/login-path"
        assert body["normalized_url"] == "http://example.com/login-path"

    async def test_conserva_url_original_con_espacios(self, client: httpx.AsyncClient) -> None:
        response = await client.post("/api/v1/analyze", json={"url": "  http://example.com/demo  "})
        assert response.status_code == 200
        assert response.json()["url_analyzed"] == "  http://example.com/demo  "
        assert response.json()["normalized_url"] == "http://example.com/demo"


class TestAnalyzeErrores:
    """Mapeo de errores de entrada a 400/422."""

    async def test_texto_plano_400(self, client: httpx.AsyncClient) -> None:
        response = await client.post(
            "/api/v1/analyze", json={"url": "hola mundo este no es un link"}
        )
        assert response.status_code == 400
        assert response.json() == {
            "error": {
                "code": "invalid_url",
                "message": "La entrada no corresponde a un enlace válido",
            }
        }

    async def test_url_demasiado_larga_400(self, client: httpx.AsyncClient) -> None:
        response = await client.post("/api/v1/analyze", json={"url": "x" * 4097})
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "url_too_long"
        assert "4096 caracteres" in response.json()["error"]["message"]

    async def test_url_corta_422(self, client: httpx.AsyncClient) -> None:
        response = await client.post("/api/v1/analyze", json={"url": "ab"})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"

    async def test_url_ausente_422(self, client: httpx.AsyncClient) -> None:
        response = await client.post("/api/v1/analyze", json={})
        assert response.status_code == 422

    async def test_error_no_controlado_500_sin_trazas(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _falla(_: str) -> None:
            raise RuntimeError("detalle-interno-secreto")

        monkeypatch.setattr("app.services.analyzer.normalize", _falla)
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as http_client:
            response = await http_client.post("/api/v1/analyze", json={"url": VALID_URL})

        assert response.status_code == 500
        assert response.json()["error"]["code"] == "internal_error"
        assert "detalle-interno-secreto" not in response.text
        assert "Traceback" not in response.text


class TestCors:
    """CORS restringido a los orígenes configurados."""

    async def test_origen_permitido(self, client: httpx.AsyncClient) -> None:
        response = await client.options(
            "/api/v1/analyze",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "http://localhost:5173"

    async def test_origen_no_permitido(self, client: httpx.AsyncClient) -> None:
        response = await client.options(
            "/api/v1/analyze",
            headers={
                "Origin": "http://evil.example",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert response.status_code == 400
        assert "access-control-allow-origin" not in response.headers

    async def test_sin_origen_no_agrega_cabecera(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/health")
        assert response.status_code == 200
        assert "access-control-allow-origin" not in response.headers


class TestAnalyzeConReputacion:
    """El endpoint delega en el orquestador y refleja PhishTank (H3-T06)."""

    async def test_match_phishtank_suma_50_y_fuerza_alto(
        self, client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class _ClienteMatch:
            async def check_url(self, url: str) -> PhishtankResult:
                return PhishtankResult(is_match=True, status=PhishtankStatus.AVAILABLE)

        monkeypatch.setattr("app.services.analyzer.get_phishtank_client", lambda: _ClienteMatch())

        response = await client.post("/api/v1/analyze", json={"url": VALID_URL})

        assert response.status_code == 200
        body = response.json()
        assert body["score"] == 50
        assert body["risk_level"] == "Alto"
        assert body["phishtank_status"] == "available"
        assert "MATCH_PHISHTANK" in {e["rule_id"] for e in body["evidences"]}

    async def test_timeout_devuelve_200_con_analisis_lexico(
        self, client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class _ClienteTimeout:
            async def check_url(self, url: str) -> PhishtankResult:
                return PhishtankResult(is_match=False, status=PhishtankStatus.TIMEOUT)

        monkeypatch.setattr("app.services.analyzer.get_phishtank_client", lambda: _ClienteTimeout())

        response = await client.post("/api/v1/analyze", json={"url": "http://10.0.0.1/login"})

        assert response.status_code == 200
        body = response.json()
        assert body["phishtank_status"] == "timeout"
        assert body["score"] == 40
        assert body["risk_level"] == "Medio"
