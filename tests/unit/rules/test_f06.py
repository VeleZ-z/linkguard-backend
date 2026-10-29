"""Pruebas unitarias de F06 — símbolo ``@`` (RF-206, TC-F06, R-EDGE-04)."""

from __future__ import annotations

import pytest
from app.engine.rules.f06_at_symbol import POINTS, RULE_ID, evaluate_at_symbol
from app.normalization import normalize


class TestF06AtSymbol:
    """La regla se activa cuando ``@`` aparece en el host o en el path."""

    @pytest.mark.parametrize(
        "url",
        [
            "http://user@evil.example/login",
            "http://a@b@evil.example/login",
            "http://example.com/a@b",
            "http://example.com/user@example.com/profile",
        ],
    )
    def test_tc_f06_p_detecta_arroba(self, url: str) -> None:
        result = evaluate_at_symbol(normalize(url))

        assert result.activated is True
        assert result.rule_id == RULE_ID
        assert result.points == POINTS == 20

    @pytest.mark.parametrize(
        "url",
        [
            "http://example.com/login",
            "http://sub.example.com/path/to/resource",
        ],
    )
    def test_no_activa_sin_arroba(self, url: str) -> None:
        result = evaluate_at_symbol(normalize(url))

        assert result.activated is False
        assert result.points == 0

    def test_es_pura_y_determinista(self) -> None:
        parsed = normalize("http://user@evil.example/login")

        assert evaluate_at_symbol(parsed) == evaluate_at_symbol(parsed)
