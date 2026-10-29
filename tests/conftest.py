"""Fixtures reutilizables para la suite de pruebas de LinkGuard.

Provee objetos de prueba (DTOs, modelos internos y pesos) compartidos por
los módulos de prueba unitaria e integración, sin dependencias de red.
"""

from __future__ import annotations

from typing import Final

import pytest
from app.engine.models import ParsedURL, RuleResult
from app.engine.weights import WEIGHTS
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
