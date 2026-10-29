"""Pruebas unitarias de F10 — ratio de especiales (RF-210, TC-F10)."""

from __future__ import annotations

import pytest
from app.engine.models import ParsedURL
from app.engine.rules.f10_special_chars_ratio import (
    MAX_RATIO,
    POINTS,
    RULE_ID,
    evaluate_special_chars_ratio,
    special_chars_ratio,
)
from app.normalization import normalize


def _manual(url: str) -> ParsedURL:
    return ParsedURL(
        scheme="http",
        netloc="example.com",
        host="example.com",
        normalized_url=url,
    )


class TestSpecialCharsRatio:
    """Cálculo puro de la proporción de ``? = % - _ &``."""

    def test_cadena_vacia(self) -> None:
        assert special_chars_ratio("") == 0.0

    def test_sin_especiales(self) -> None:
        assert special_chars_ratio("http://example.com/login") == 0.0

    def test_proporcion_conocida(self) -> None:
        assert special_chars_ratio("abcd????") == pytest.approx(0.5)


class TestF10SpecialCharsRatio:
    """La regla se activa con un ratio estrictamente mayor a 0.15."""

    def test_tc_f10_p_parametros_inundados(self) -> None:
        parsed = normalize("http://example.com/??????????")

        result = evaluate_special_chars_ratio(parsed)

        assert result.activated is True
        assert result.rule_id == RULE_ID
        assert result.points == POINTS == 7

    def test_url_normal_no_activa(self) -> None:
        result = evaluate_special_chars_ratio(normalize("http://example.com/login"))

        assert result.activated is False
        assert result.points == 0

    def test_frontera_exacta_de_015_no_activa(self) -> None:
        parsed = _manual("a" * 17 + "===")
        assert special_chars_ratio(parsed.normalized_url) == pytest.approx(MAX_RATIO)

        assert evaluate_special_chars_ratio(parsed).activated is False

    def test_justo_por_encima_de_015_activa(self) -> None:
        parsed = _manual("a" * 16 + "====")

        assert evaluate_special_chars_ratio(parsed).activated is True

    def test_es_pura_y_determinista(self) -> None:
        parsed = normalize("http://example.com/??????????")

        assert evaluate_special_chars_ratio(parsed) == evaluate_special_chars_ratio(parsed)
