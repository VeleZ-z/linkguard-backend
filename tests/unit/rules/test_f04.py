"""Pruebas unitarias de F04 — entropía de Shannon del host (RF-204, TC-F04)."""

from __future__ import annotations

import pytest
from app.engine.rules.f04_shannon_entropy import (
    MAX_ENTROPY,
    POINTS,
    RULE_ID,
    evaluate_shannon_entropy,
    shannon_entropy,
)
from app.normalization import normalize


class TestShannonEntropy:
    """Cálculo puro de entropía en bits por símbolo."""

    def test_cadena_vacia(self) -> None:
        assert shannon_entropy("") == 0.0

    def test_cadena_uniforme(self) -> None:
        assert shannon_entropy("aaaa") == 0.0

    def test_dos_simbolos_equiprobables(self) -> None:
        assert shannon_entropy("ab") == pytest.approx(1.0)

    def test_host_aleatorio_supera_umbral(self) -> None:
        assert shannon_entropy("abcdefghijklmnopqrstuvwxyz0123456789") > MAX_ENTROPY


class TestF04ShannonEntropy:
    """La regla se activa con entropía estrictamente mayor a 4.5."""

    def test_tc_f04_p_host_dga(self) -> None:
        parsed = normalize("http://abcdefghijklmnopqrstuvwxyz0123.com/")

        result = evaluate_shannon_entropy(parsed)

        assert shannon_entropy(parsed.host) > MAX_ENTROPY
        assert result.activated is True
        assert result.rule_id == RULE_ID
        assert result.points == POINTS == 15

    def test_host_legible_no_activa(self) -> None:
        result = evaluate_shannon_entropy(normalize("http://example.com/"))

        assert result.activated is False
        assert result.points == 0

    def test_es_pura_y_determinista(self) -> None:
        parsed = normalize("http://example.com/")

        assert evaluate_shannon_entropy(parsed) == evaluate_shannon_entropy(parsed)
