"""Pruebas unitarias de F03 — subdominios múltiples (RF-203, TC-F03)."""

from __future__ import annotations

import pytest
from app.engine.models import ParsedURL
from app.engine.rules.f03_multiple_subdomains import (
    POINTS,
    RULE_ID,
    evaluate_multiple_subdomains,
)
from app.normalization import normalize


def _manual(host: str, *, is_ip: bool = False) -> ParsedURL:
    """Construye un ParsedURL mínimo para aislar el conteo de subdominios."""
    return ParsedURL(
        scheme="http",
        netloc=host,
        host=host,
        normalized_url=f"http://{host}/",
        is_ip=is_ip,
    )


class TestF03MultipleSubdomains:
    """La regla se activa con tres o más niveles de subdominio."""

    def test_tc_f03_p_tres_subdominios(self) -> None:
        result = evaluate_multiple_subdomains(_manual("a.b.c.example.com"))

        assert result.activated is True
        assert result.rule_id == RULE_ID
        assert result.points == POINTS == 10

    def test_dos_subdominios_no_activa(self) -> None:
        result = evaluate_multiple_subdomains(_manual("a.b.example.com"))

        assert result.activated is False
        assert result.points == 0

    def test_dominio_raiz_no_activa(self) -> None:
        assert evaluate_multiple_subdomains(_manual("example.com")).activated is False

    def test_respeta_sufijos_multinivel(self) -> None:
        assert evaluate_multiple_subdomains(_manual("a.b.example.co.uk")).activated is False
        assert evaluate_multiple_subdomains(_manual("a.b.c.example.co.uk")).activated is True

    def test_desde_normalizacion_real(self) -> None:
        result = evaluate_multiple_subdomains(normalize("http://a.b.c.example.com/login"))

        assert result.activated is True
        assert result.points == POINTS == 10

    @pytest.mark.parametrize("host", ["10.0.0.1", "127.0.0.1", "::1"])
    def test_ip_nunca_activa(self, host: str) -> None:
        result = evaluate_multiple_subdomains(_manual(host, is_ip=True))

        assert result.activated is False
        assert result.points == 0

    def test_es_pura_y_determinista(self) -> None:
        parsed = _manual("a.b.c.example.com")

        assert evaluate_multiple_subdomains(parsed) == evaluate_multiple_subdomains(parsed)
