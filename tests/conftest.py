"""Fixtures reutilizables para la suite de pruebas de LinkGuard.

Provee objetos de prueba (DTOs, modelos internos y pesos) compartidos por
los módulos de prueba unitaria e integración, sin dependencias de red.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Final

import httpx
import pytest
from app.clients.phishtank import PhishtankResult
from app.core.rate_limit import limiter
from app.engine.models import ParsedURL, RuleResult
from app.engine.weights import WEIGHTS
from app.main import app
from app.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    EvidenceDTO,
    PhishtankStatus,
    RiskLevel,
)

# --- Constantes de prueba --------------------------------------------------

VALID_URL_SHORT: Final[str] = "http://example.com"
VALID_URL_LONG: Final[str] = "https://subdomain.example.com/login-path?q=1#section"
TOO_LONG_URL: Final[str] = "x" * 4097
MIN_URL: Final[str] = "a" * 3
MAX_URL: Final[str] = "x" * 4096


# --- Aislamiento de red -----------------------------------------------------


@pytest.fixture(autouse=True)
def _phishtank_sin_red(monkeypatch: pytest.MonkeyPatch) -> None:
    """Impide cualquier salida real a PhishTank durante la suite.

    El endpoint delega en ``analyzer.analyze_url``; este parche sustituye el
    cliente único por uno neutro que simula la indisponibilidad del servicio
    externo. Las pruebas que necesiten respuestas concretas deben inyectar su
    propio cliente en ``analyze_url(..., client=...)`` o redefinir el parche
    con ``monkeypatch`` dentro de la propia prueba.
    """

    class _ClienteSinRed:
        """Doble de prueba que nunca abre sockets."""

        async def check_url(self, url: str) -> PhishtankResult:
            return PhishtankResult(is_match=False, status=PhishtankStatus.UNAVAILABLE)

    monkeypatch.setattr(
        "app.services.analyzer.get_phishtank_client",
        lambda: _ClienteSinRed(),
    )


# --- Fixtures de DTOs -------------------------------------------------------


@pytest.fixture
def valid_request() -> AnalyzeRequest:
    """Solicitud de análisis válida (URL mínima aceptable)."""
    return AnalyzeRequest(url="http://example.com/login-path")


@pytest.fixture
def sample_parsed_url() -> ParsedURL:
    """ParsedURL representativo de una URL normalizada."""
    return ParsedURL(
        scheme="http",
        netloc="subdomain.example.com:8080",
        host="subdomain.example.com",
        port=8080,
        path="/login-path",
        params="",
        query="q=1",
        fragment="section",
        normalized_url="http://subdomain.example.com:8080/login-path?q=1#section",
    )


@pytest.fixture
def sample_rule_result() -> RuleResult:
    """RuleResult representativo de una regla activada."""
    return RuleResult(
        rule_id="F02_DIRECT_IP",
        activated=True,
        points=25,
        title="Dirección IP directa",
        description="El host de la URL es una dirección IPv4/IPv6.",
    )


@pytest.fixture
def sample_evidence() -> EvidenceDTO:
    """EvidenciaDTO representativa."""
    return EvidenceDTO(
        rule_id="F11_SOCIAL_ENGINEERING_KEYWORDS",
        points=15,
        title="Palabras clave de ingeniería social",
        description="Se detectaron términos sensibles asociados a suplantación.",
    )


@pytest.fixture
def sample_response() -> AnalyzeResponse:
    """AnalyzeResponse representativo con score medio."""
    return AnalyzeResponse(
        url_analyzed="https://subdomain.example.com/login-path",
        normalized_url="http://subdomain.example.com/login-path",
        score=45,
        risk_level=RiskLevel.MEDIO,
        recommendation=(
            "El enlace presenta características inusuales o sospechosas. "
            "Verifique la identidad del remitente antes de interactuar."
        ),
        evidences=[
            EvidenceDTO(
                rule_id="F02_DIRECT_IP",
                points=25,
                title="Dirección IP directa",
                description="El host es una dirección IP directa.",
            ),
            EvidenceDTO(
                rule_id="F08_SCHEMA_REDIRECT",
                points=20,
                title="Desvío de esquema en path/query",
                description="Se detectó 'http:' dentro del path o query.",
            ),
        ],
        phishtank_status=PhishtankStatus.AVAILABLE,
        execution_time_ms=38.45,
    )


# --- Accesores de valores esperados ----------------------------------------


@pytest.fixture
def expected_weights() -> dict[str, int]:
    """Matriz de pesos wᵢ esperada según el contrato §3."""
    return dict(WEIGHTS)


# --- Cliente ASGI compartido -------------------------------------------------


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    """Cliente ASGI sin red real para pruebas de integración."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client


@pytest.fixture(autouse=True)
def _reset_rate_limiter_global() -> None:
    """Evita que el contador de slowapi se filtre entre pruebas."""
    limiter.reset()
    yield
    limiter.reset()
