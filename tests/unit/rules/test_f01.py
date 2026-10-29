"""Pruebas unitarias de F01 — longitud excesiva (RF-201, TC-F01)."""

from __future__ import annotations

from app.engine.rules.f01_excessive_length import (
    MIN_LENGTH,
    POINTS,
    RULE_ID,
    evaluate_excessive_length,
)
from app.normalization import normalize


def _url_de_longitud(total: int) -> str:
    base = "http://example.com/"
    return base + "a" * (total - len(base))


class TestF01ExcessiveLength:
    """La regla se activa con 75 caracteres normalizados o más."""

    def test_tc_f01_p_80_caracteres(self) -> None:
        parsed = normalize(_url_de_longitud(80))
        assert len(parsed.normalized_url) == 80

        result = evaluate_excessive_length(parsed)

        assert result.activated is True
        assert result.rule_id == RULE_ID
        assert result.points == POINTS == 10
        assert result.title

    def test_tc_f01_n_45_caracteres(self) -> None:
        parsed = normalize(_url_de_longitud(45))
        assert len(parsed.normalized_url) == 45

        result = evaluate_excessive_length(parsed)

        assert result.activated is False
        assert result.rule_id == RULE_ID
        assert result.points == 0

    def test_frontera_exacta_de_75(self) -> None:
        parsed = normalize(_url_de_longitud(MIN_LENGTH))
        assert len(parsed.normalized_url) == MIN_LENGTH

        assert evaluate_excessive_length(parsed).activated is True

    def test_justo_por_debajo_de_75(self) -> None:
        parsed = normalize(_url_de_longitud(MIN_LENGTH - 1))

        assert evaluate_excessive_length(parsed).activated is False

    def test_es_pura_y_determinista(self) -> None:
        parsed = normalize(_url_de_longitud(80))

        assert evaluate_excessive_length(parsed) == evaluate_excessive_length(parsed)
