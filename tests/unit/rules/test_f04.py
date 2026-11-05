"""Pruebas unitarias de F04 — entropía de Shannon adaptativa (RF-204, TC-F04)."""

from __future__ import annotations

import math

import pytest
from app.engine.models import ParsedURL
from app.engine.rules.f04_shannon_entropy import (
    MAX_ENTROPY,
    MIN_LABEL_LENGTH,
    POINTS,
    RULE_ID,
    evaluate_shannon_entropy,
    shannon_entropy,
)
from app.normalization import normalize

#: Etiqueta aleatoria con 26 símbolos distintos: H = log2(26) ≈ 4.70 > 4.5.
RANDOM_LABEL = "qwertyuiopasdfghjklzxcvbnm"


class TestShannonEntropy:
    """Cálculo puro de entropía en bits por símbolo."""

    def test_cadena_vacia(self) -> None:
        assert shannon_entropy("") == 0.0

    def test_cadena_uniforme(self) -> None:
        assert shannon_entropy("aaaa") == 0.0

    def test_dos_simbolos_equiprobables(self) -> None:
        assert shannon_entropy("ab") == pytest.approx(1.0)

    def test_etiqueta_aleatoria_supera_umbral(self) -> None:
        assert shannon_entropy(RANDOM_LABEL) > MAX_ENTROPY


class TestF04ShannonEntropy:
    """La regla se activa con entropía estrictamente mayor a 4.5."""

    def test_tc_f04_p_dominio_dga_sin_subdominios(self) -> None:
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

    @pytest.mark.parametrize("url", ["http://10.0.0.1/login", "http://[2001:db8::1]/"])
    def test_host_ip_no_evalua_entropia(self, url: str) -> None:
        """F02 gestiona las IP literales; F04 no debe duplicar la señal."""
        result = evaluate_shannon_entropy(normalize(url))

        assert result.activated is False
        assert result.points == 0

    def test_subdominio_aleatorio_activa(self) -> None:
        parsed = normalize(f"http://{RANDOM_LABEL}.bringyournewproduct.org/")

        assert parsed.subdomains == [RANDOM_LABEL]
        assert evaluate_shannon_entropy(parsed).activated is True

    def test_subdominio_legible_no_activa(self) -> None:
        parsed = normalize("http://secure-login.bringyournewproduct.org/")

        assert evaluate_shannon_entropy(parsed).activated is False

    def test_con_subdominios_no_evalua_el_dominio_registrable(self) -> None:
        """La regla mide las etiquetas de subdominio, no el dominio base."""
        parsed = normalize(f"http://a.{RANDOM_LABEL}.com/")

        assert parsed.subdomains == ["a"]
        assert parsed.main_domain == f"{RANDOM_LABEL}.com"
        assert evaluate_shannon_entropy(parsed).activated is False

    def test_sin_subdominios_evalua_el_dominio_registrable(self) -> None:
        parsed = normalize(f"http://{RANDOM_LABEL}.com/")

        assert parsed.subdomains == []
        assert evaluate_shannon_entropy(parsed).activated is True

    def test_sufijo_publico_multietiqueta(self) -> None:
        parsed = normalize(f"http://{RANDOM_LABEL}.co.uk/")

        assert parsed.subdomains == []
        assert parsed.main_domain == f"{RANDOM_LABEL}.co.uk"
        assert evaluate_shannon_entropy(parsed).activated is True

    def test_construccion_manual_usa_la_public_suffix_list(self) -> None:
        parsed = ParsedURL(
            scheme="http",
            netloc=f"{RANDOM_LABEL}.example.com",
            host=f"{RANDOM_LABEL}.example.com",
            normalized_url=f"http://{RANDOM_LABEL}.example.com/",
        )

        assert evaluate_shannon_entropy(parsed).activated is True

    def test_construccion_manual_detecta_ip(self) -> None:
        parsed = ParsedURL(
            scheme="http",
            netloc="10.0.0.1",
            host="10.0.0.1",
            normalized_url="http://10.0.0.1/",
        )

        assert evaluate_shannon_entropy(parsed).activated is False

    def test_etiqueta_del_enunciado_no_supera_el_umbral(self) -> None:
        """Documenta por qué el ejemplo literal no puede activar la regla.

        ``wjueujzktghdjopdhl`` tiene 18 símbolos y H ≈ 3.57. Aun con 18
        símbolos todos distintos, la entropía máxima sería ``log2(18) ≈ 4.17``,
        por debajo del umbral 4.5. Para activar F04 hacen falta al menos 23
        símbolos distintos (``2**4.5 ≈ 22.6``).
        """
        label = "wjueujzktghdjopdhl"

        assert len(label) < 2**MAX_ENTROPY
        assert shannon_entropy(label) == pytest.approx(3.57, abs=0.01)
        assert math.log2(len(label)) < MAX_ENTROPY
        assert (
            evaluate_shannon_entropy(
                normalize(f"http://{label}.bringyournewproduct.org/")
            ).activated
            is False
        )

    def test_longitud_minima_de_etiqueta(self) -> None:
        """Una etiqueta de 6 símbolos nunca alcanza 4.5 bits (máx. log2(6))."""
        assert math.log2(MIN_LABEL_LENGTH) < MAX_ENTROPY

    def test_es_pura_y_determinista(self) -> None:
        parsed = normalize("http://example.com/")

        assert evaluate_shannon_entropy(parsed) == evaluate_shannon_entropy(parsed)
