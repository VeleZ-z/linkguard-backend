"""Pruebas unitarias de los DTOs del contrato de API (contrato §6).

Valida los límites sintácticos exactos de ``AnalyzeRequest`` (3 a 4096
caracteres), el rechazo de cadenas vacías/cortas/nulas, y la serialización
JSON correcta de los enums ``RiskLevel`` y ``PhishtankStatus``.
"""

from __future__ import annotations

import pytest
from app.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    EvidenceDTO,
    PhishtankStatus,
    RiskLevel,
)
from pydantic import ValidationError


class TestRiskLevel:
    """Validación del enum de niveles de riesgo (RF-302)."""

    @pytest.mark.parametrize(
        "member,expected",
        [
            (RiskLevel.BAJO, "Bajo"),
            (RiskLevel.MEDIO, "Medio"),
            (RiskLevel.ALTO, "Alto"),
        ],
    )
    def test_valores_permitidos(self, member: RiskLevel, expected: str) -> None:
        assert member.value == expected

    def test_serializacion_json(self) -> None:
        """OpenAPI/JSON expone los valores permitidos sin alterar el wire."""
        assert [m.value for m in RiskLevel] == ["Bajo", "Medio", "Alto"]


class TestPhishtankStatus:
    """Validación del enum de estado de reputación externa (RF-404)."""

    @pytest.mark.parametrize(
        "member,expected",
        [
            (PhishtankStatus.AVAILABLE, "available"),
            (PhishtankStatus.TIMEOUT, "timeout"),
            (PhishtankStatus.UNAVAILABLE, "unavailable"),
            (PhishtankStatus.CACHED, "cached"),
        ],
    )
    def test_valores_permitidos(self, member: PhishtankStatus, expected: str) -> None:
        assert member.value == expected

    def test_serializacion_json(self) -> None:
        assert [m.value for m in PhishtankStatus] == [
            "available",
            "timeout",
            "unavailable",
            "cached",
        ]


class TestAnalyzeRequest:
    """Validación de la solicitud de análisis (RF-101, RF-105)."""

    def test_url_valida_limite_minimo(self) -> None:
        """URL de exactamente 3 caracteres es aceptada."""
        req = AnalyzeRequest(url="a" * 3)
        assert req.url == "a" * 3

    def test_url_valida_limite_maximo(self) -> None:
        """URL de exactamente 4096 caracteres es aceptada."""
        req = AnalyzeRequest(url="x" * 4096)
        assert req.url == "x" * 4096

    def test_url_corta_es_rechazada(self) -> None:
        """URL de 2 caracteres debe fallar la validación."""
        with pytest.raises(ValidationError):
            AnalyzeRequest(url="ab")

    def test_url_vacia_es_rechazada(self) -> None:
        """Cadena vacía debe fallar la validación."""
        with pytest.raises(ValidationError):
            AnalyzeRequest(url="")

    def test_url_sin_campos_es_rechazada(self) -> None:
        """Falta el campo obligatorio 'url'."""
        with pytest.raises(ValidationError):
            AnalyzeRequest()  # type: ignore[call-arg]

    def test_url_exceso_maximo_es_rechazada(self) -> None:
        """URL de 4097 caracteres debe fallar la validación."""
        with pytest.raises(ValidationError):
            AnalyzeRequest(url="x" * 4097)

    def test_url_nula_es_rechazada(self) -> None:
        """Valor nulo para 'url' debe fallar la validación."""
        with pytest.raises(ValidationError):
            AnalyzeRequest(url=None)  # type: ignore[arg-type]


class TestEvidenceDTO:
    """Validación del DTO de evidencia individual (RF-303)."""

    def test_instanciacion_correcta(self, sample_evidence: EvidenceDTO) -> None:
        assert sample_evidence.rule_id == "F11_SOCIAL_ENGINEERING_KEYWORDS"
        assert sample_evidence.points == 15
        assert sample_evidence.title == "Palabras clave de ingeniería social"
        assert "términos sensibles" in sample_evidence.description

    def test_serializacion_json(self, sample_evidence: EvidenceDTO) -> None:
        data = sample_evidence.model_dump(mode="json")
        assert data == {
            "rule_id": "F11_SOCIAL_ENGINEERING_KEYWORDS",
            "points": 15,
            "title": "Palabras clave de ingeniería social",
            "description": "Se detectaron términos sensibles asociados a suplantación.",
        }

    def test_points_no_negativos(self) -> None:
        """Los puntos no pueden ser negativos."""
        with pytest.raises(ValidationError):
            EvidenceDTO(
                rule_id="F01",
                points=-1,
                title="x",
                description="desc",
            )


class TestAnalyzeResponse:
    """Validación de la respuesta de análisis (contrato §6)."""

    def test_instanciacion_correcta(self, sample_response: AnalyzeResponse) -> None:
        assert sample_response.score == 45
        assert sample_response.risk_level == RiskLevel.MEDIO
        assert sample_response.phishtank_status == PhishtankStatus.AVAILABLE
        assert sample_response.execution_time_ms == 38.45
        assert len(sample_response.evidences) == 2

    def test_serializacion_json_enums(self, sample_response: AnalyzeResponse) -> None:
        """Los enums se serializan como sus valores de cadena en JSON."""
        data = sample_response.model_dump(mode="json")
        assert data["risk_level"] == "Medio"
        assert data["phishtank_status"] == "available"
        assert set(data) == {
            "url_analyzed",
            "normalized_url",
            "score",
            "risk_level",
            "recommendation",
            "evidences",
            "phishtank_status",
            "execution_time_ms",
        }

    def test_score_fuera_de_rango_es_rechazado(self) -> None:
        """Score > 100 debe fallar la validación."""
        with pytest.raises(ValidationError):
            AnalyzeResponse(
                url_analyzed="http://example.com",
                normalized_url="http://example.com",
                score=101,
                risk_level=RiskLevel.ALTO,
                recommendation="desc",
                evidences=[],
                phishtank_status=PhishtankStatus.AVAILABLE,
                execution_time_ms=1.0,
            )

    def test_score_negativo_es_rechazado(self) -> None:
        """Score < 0 debe fallar la validación."""
        with pytest.raises(ValidationError):
            AnalyzeResponse(
                url_analyzed="http://example.com",
                normalized_url="http://example.com",
                score=-1,
                risk_level=RiskLevel.ALTO,
                recommendation="desc",
                evidences=[],
                phishtank_status=PhishtankStatus.AVAILABLE,
                execution_time_ms=1.0,
            )

    def test_enum_riesgo_invalido_es_rechazado(self) -> None:
        """Valor de risk_level no permitido debe fallar."""
        with pytest.raises(ValidationError):
            AnalyzeResponse(
                url_analyzed="http://example.com",
                normalized_url="http://example.com",
                score=50,
                risk_level="Crítico",  # type: ignore[arg-type]
                recommendation="desc",
                evidences=[],
                phishtank_status=PhishtankStatus.AVAILABLE,
                execution_time_ms=1.0,
            )

    def test_enum_phishtank_invalido_es_rechazado(self) -> None:
        """Valor de phishtank_status no permitido debe fallar."""
        with pytest.raises(ValidationError):
            AnalyzeResponse(
                url_analyzed="http://example.com",
                normalized_url="http://example.com",
                score=50,
                risk_level=RiskLevel.ALTO,
                recommendation="desc",
                evidences=[],
                phishtank_status="pendiente",  # type: ignore[arg-type]
                execution_time_ms=1.0,
            )

    def test_tiempo_ejecucion_negativo_es_rechazado(self) -> None:
        """execution_time_ms < 0 debe fallar la validación."""
        with pytest.raises(ValidationError):
            AnalyzeResponse(
                url_analyzed="http://example.com",
                normalized_url="http://example.com",
                score=50,
                risk_level=RiskLevel.ALTO,
                recommendation="desc",
                evidences=[],
                phishtank_status=PhishtankStatus.AVAILABLE,
                execution_time_ms=-0.5,
            )

    def test_campos_requeridos(self) -> None:
        """Todos los campos del contrato §6 son obligatorios."""
        with pytest.raises(ValidationError):
            AnalyzeResponse(  # type: ignore[call-arg]
                url_analyzed="http://example.com",
            )
