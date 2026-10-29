"""Pruebas unitarias de F07 — guiones en el dominio (RF-207, TC-F07)."""

from __future__ import annotations

import pytest
from app.engine.models import ParsedURL
from app.engine.rules.f07_hyphens_in_domain import (
    MIN_HYPHENS,
    POINTS,
    RULE_ID,
    evaluate_hyphens_in_domain,
)
from app.normalization import normalize


def _manual(host: str, main_domain: str | None, *, is_ip: bool = False) -> ParsedURL:
    return ParsedURL(
        scheme="http",
        netloc=host,
        host=host,
        normalized_url=f"http://{host}/",
        main_domain=main_domain,
        is_ip=is_ip,
    )


class TestF07HyphensInDomain:
    """La regla cuenta guiones solo en el dominio principal (eTLD+1)."""

    @pytest.mark.parametrize(
        "url",
        [
            "http://secure-login-verify.com/",
            "http://my--bank.com/",
            "http://a-b-c.co.uk/",
        ],
    )
    def test_tc_f07_p_dos_o_mas_guiones(self, url: str) -> None:
        result = evaluate_hyphens_in_domain(normalize(url))

        assert result.activated is True
        assert result.rule_id == RULE_ID
        assert result.points == POINTS == 8

    @pytest.mark.parametrize(
        "url",
        [
            "http://example.com/",
            "http://secure-login.com/",
            "http://a-b-c.example.com/",
        ],
    )
    def test_no_activa_con_menos_de_dos_guiones(self, url: str) -> None:
        result = evaluate_hyphens_in_domain(normalize(url))

        assert result.activated is False
        assert result.points == 0

    def test_no_cuenta_guiones_en_subdominios(self) -> None:
        result = evaluate_hyphens_in_domain(_manual("a-b-c.example.com", "example.com"))

        assert result.activated is False

    def test_ip_nunca_activa(self) -> None:
        result = evaluate_hyphens_in_domain(_manual("10.0.0.1", None, is_ip=True))

        assert result.activated is False

    def test_umbral_es_dos(self) -> None:
        assert MIN_HYPHENS == 2
        assert evaluate_hyphens_in_domain(_manual("a-b.com", "a-b.com")).activated is False
