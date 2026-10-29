"""Pruebas unitarias de F09 — puerto no estándar (RF-209, TC-F09)."""

from __future__ import annotations

import pytest
from app.engine.rules.f09_non_standard_port import (
    POINTS,
    RULE_ID,
    STANDARD_PORTS,
    evaluate_non_standard_port,
)
from app.normalization import normalize


class TestF09NonStandardPort:
    """La regla se activa con un puerto explícito fuera de {80, 443}."""

    @pytest.mark.parametrize(
        "url",
        [
            "http://example.com:8080/login",
            "https://example.com:8443/login",
            "http://example.com:21/login",
            "http://example.com:65535/",
        ],
    )
    def test_tc_f09_p_puerto_no_estandar(self, url: str) -> None:
        result = evaluate_non_standard_port(normalize(url))

        assert result.activated is True
        assert result.rule_id == RULE_ID
        assert result.points == POINTS == 10

    @pytest.mark.parametrize(
        "url",
        [
            "http://example.com/login",
            "https://example.com/login",
            "http://example.com:80/login",
            "https://example.com:443/login",
        ],
    )
    def test_no_activa_sin_puerto_o_puerto_estandar(self, url: str) -> None:
        result = evaluate_non_standard_port(normalize(url))

        assert result.activated is False
        assert result.points == 0

    def test_puertos_estandar_documentados(self) -> None:
        assert STANDARD_PORTS == frozenset({80, 443})

    def test_es_pura_y_determinista(self) -> None:
        parsed = normalize("http://example.com:8080/login")

        assert evaluate_non_standard_port(parsed) == evaluate_non_standard_port(parsed)
