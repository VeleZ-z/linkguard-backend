"""Pruebas unitarias de F11 — palabras clave sensibles (RF-211, TC-F11)."""

from __future__ import annotations

import pytest
from app.engine.data.sensitive_keywords import SENSITIVE_KEYWORDS
from app.engine.rules.f11_social_engineering_keywords import (
    POINTS,
    RULE_ID,
    evaluate_social_engineering_keywords,
)
from app.normalization import normalize


class TestF11SocialEngineeringKeywords:
    """La regla se activa ante términos sensibles en host, path o query."""

    @pytest.mark.parametrize(
        "url",
        [
            "http://secure-login.example.com/",
            "http://example.com/account/verify",
            "https://example.com/bank/update",
            "https://example.com/go?service=signin",
            "https://example.com/SECURE/LOGIN",
        ],
    )
    def test_tc_f11_p_detecta_palabras_clave(self, url: str) -> None:
        result = evaluate_social_engineering_keywords(normalize(url))

        assert result.activated is True
        assert result.rule_id == RULE_ID
        assert result.points == POINTS == 15

    @pytest.mark.parametrize(
        "url",
        [
            "http://example.com/products",
            "https://docs.example.org/guide",
            "http://example.com/news/2026",
        ],
    )
    def test_no_activa_sin_palabras_clave(self, url: str) -> None:
        result = evaluate_social_engineering_keywords(normalize(url))

        assert result.activated is False
        assert result.points == 0

    def test_catalogo_contiene_los_ocho_terminos(self) -> None:
        assert SENSITIVE_KEYWORDS == frozenset(
            {
                "login",
                "bank",
                "verify",
                "account",
                "update",
                "secure",
                "signin",
                "service",
            }
        )

    def test_es_pura_y_determinista(self) -> None:
        parsed = normalize("http://secure-login.example.com/")

        assert evaluate_social_engineering_keywords(parsed) == evaluate_social_engineering_keywords(
            parsed
        )
