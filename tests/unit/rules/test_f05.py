"""Pruebas unitarias de F05 — acortador de URL (RF-205, TC-F05)."""

from __future__ import annotations

import pytest
from app.engine.data.url_shorteners import URL_SHORTENERS
from app.engine.models import ParsedURL
from app.engine.rules.f05_url_shortener import POINTS, RULE_ID, evaluate_url_shortener
from app.normalization import normalize


def _manual(host: str, *, is_ip: bool = False) -> ParsedURL:
    return ParsedURL(
        scheme="http",
        netloc=host,
        host=host,
        normalized_url=f"http://{host}/",
        is_ip=is_ip,
    )


class TestF05UrlShortener:
    """La regla se activa con dominios acortadores conocidos o sus subdominios."""

    @pytest.mark.parametrize(
        "url",
        [
            "http://bit.ly/abc123",
            "https://BIT.LY/abc123",
            "http://www.bit.ly/abc123",
            "http://tinyurl.com/abc123",
            "http://t.co/abc123",
        ],
    )
    def test_tc_f05_p_detecta_acortador(self, url: str) -> None:
        result = evaluate_url_shortener(normalize(url))

        assert result.activated is True
        assert result.rule_id == RULE_ID
        assert result.points == POINTS == 15

    @pytest.mark.parametrize(
        "url",
        [
            "http://example.com/abc123",
            "http://notbit.ly/abc123",
            "http://bit.ly.example.com/",
        ],
    )
    def test_no_activa_con_dominio_normal(self, url: str) -> None:
        result = evaluate_url_shortener(normalize(url))

        assert result.activated is False
        assert result.points == 0

    def test_ip_nunca_activa(self) -> None:
        result = evaluate_url_shortener(_manual("10.0.0.1", is_ip=True))

        assert result.activated is False

    def test_catalogo_es_inmutable(self) -> None:
        assert isinstance(URL_SHORTENERS, frozenset)
        assert "bit.ly" in URL_SHORTENERS
