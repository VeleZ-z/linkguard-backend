"""Pruebas unitarias de F02 — dirección IP directa (RF-202, TC-F02, R-EDGE-03)."""

from __future__ import annotations

import pytest
from app.engine.rules.f02_direct_ip import POINTS, RULE_ID, evaluate_direct_ip
from app.normalization import normalize


class TestF02DirectIP:
    """La regla se activa con hosts IPv4/IPv6 literales."""

    @pytest.mark.parametrize(
        "url",
        [
            "http://10.0.0.1/login",
            "http://255.255.255.255/",
            "http://0177.0.0.1/login",
            "http://0x7f.0.0.1/login",
            "http://[::1]/login",
            "http://[2001:db8::1]/login",
        ],
    )
    def test_tc_f02_p_detecta_ip_literal(self, url: str) -> None:
        result = evaluate_direct_ip(normalize(url))

        assert result.activated is True
        assert result.rule_id == RULE_ID
        assert result.points == POINTS == 25

    @pytest.mark.parametrize(
        "url",
        [
            "http://example.com/login",
            "http://sub.example.com/",
            "http://10.0.0.1.example.com/",
            "http://1.2.3/",
            "http://256.0.0.1/",
        ],
    )
    def test_no_activa_con_dominio_o_ip_invalida(self, url: str) -> None:
        result = evaluate_direct_ip(normalize(url))

        assert result.activated is False
        assert result.points == 0

    def test_octal_y_hexadecimal_equivalen_a_decimal(self) -> None:
        decimal = evaluate_direct_ip(normalize("http://127.0.0.1/"))
        octal = evaluate_direct_ip(normalize("http://0177.0.0.1/"))
        hexadecimal = evaluate_direct_ip(normalize("http://0x7f.0.0.1/"))

        assert decimal.activated is octal.activated is hexadecimal.activated is True
