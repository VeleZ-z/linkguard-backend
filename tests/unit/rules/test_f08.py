"""Pruebas unitarias de F08 — desvío de esquema (RF-208, TC-F08)."""

from __future__ import annotations

import pytest
from app.engine.rules.f08_schema_redirect import (
    POINTS,
    RULE_ID,
    evaluate_schema_redirect,
)
from app.normalization import normalize


class TestF08SchemaRedirect:
    """La regla se activa con ``http:``/``https:`` en path o query."""

    @pytest.mark.parametrize(
        "url",
        [
            "http://example.com/http://evil.example/login",
            "http://example.com/redirect?url=https://evil.example",
            "http://example.com/go?next=HTTP://EVIL.EXAMPLE",
            "http://example.com/go?next=https%3A%2F%2Fevil.example",
        ],
    )
    def test_tc_f08_p_detecta_esquema_embebido(self, url: str) -> None:
        result = evaluate_schema_redirect(normalize(url))

        assert result.activated is True
        assert result.rule_id == RULE_ID
        assert result.points == POINTS == 20

    @pytest.mark.parametrize(
        "url",
        [
            "http://example.com/login",
            "https://example.com/path/to/resource?q=1",
            "http://example.com/http-status",
        ],
    )
    def test_no_activa_sin_esquema_embebido(self, url: str) -> None:
        result = evaluate_schema_redirect(normalize(url))

        assert result.activated is False
        assert result.points == 0

    def test_es_pura_y_determinista(self) -> None:
        parsed = normalize("http://example.com/?url=https://evil.example")

        assert evaluate_schema_redirect(parsed) == evaluate_schema_redirect(parsed)
