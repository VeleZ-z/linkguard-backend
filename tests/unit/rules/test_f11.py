"""Pruebas unitarias de F11 — palabras clave sensibles multilingües (RF-211)."""

from __future__ import annotations

import pytest
from app.engine.data.sensitive_keywords import (
    EXACT_MATCH_KEYWORDS,
    SENSITIVE_KEYWORDS,
    SENSITIVE_KEYWORDS_BY_CATEGORY,
)
from app.engine.rules.f11_social_engineering_keywords import (
    POINTS,
    RULE_ID,
    evaluate_social_engineering_keywords,
    matches_keyword,
    normalize_text,
    tokenize,
)
from app.normalization import normalize


class TestNormalizacion:
    """Normalización NFKD + ASCII + minúsculas."""

    @pytest.mark.parametrize(
        ("entrada", "esperado"),
        [
            ("Contraseña", "contrasena"),
            ("VERIFICACIÓN", "verificacion"),
            ("Cédula", "cedula"),
            ("Iniciar-Sesión", "iniciar-sesion"),
            ("AUTENTICACIÓN", "autenticacion"),
        ],
    )
    def test_elimina_diacriticos_y_minusculas(self, entrada: str, esperado: str) -> None:
        assert normalize_text(entrada) == esperado

    def test_tokeniza_por_separadores(self) -> None:
        assert tokenize("INICIAR-SESIÓN?next=paypal_soporte") == [
            "iniciar",
            "sesion",
            "next",
            "paypal",
            "soporte",
        ]


class TestCoincidenciaPorTokens:
    """La comparación evita falsos positivos de subcadenas cortas."""

    @pytest.mark.parametrize(
        ("keyword", "tokens", "esperado"),
        [
            ("pin", ["shopping"], False),
            ("pin", ["pin"], True),
            ("rut", ["routes"], False),
            ("rut", ["rut"], True),
            ("dian", ["guardian"], False),
            ("pse", ["pseudo"], False),
            ("tigo", ["vertigo"], False),
            ("login", ["securelogin"], True),
            ("login", ["loginpage"], True),
            ("password", ["passwords"], True),
            ("iniciar-sesion", ["iniciar", "sesion"], True),
            ("iniciar-sesion", ["iniciar", "otra", "sesion"], False),
            ("cuenta-bloqueada", ["cuenta", "bloqueada"], True),
        ],
    )
    def test_matches_keyword(self, keyword: str, tokens: list[str], esperado: bool) -> None:
        assert matches_keyword(keyword, tokens) is esperado


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
    def test_conserva_los_casos_previos(self, url: str) -> None:
        result = evaluate_social_engineering_keywords(normalize(url))

        assert result.activated is True
        assert result.rule_id == RULE_ID
        assert result.points == POINTS == 15

    @pytest.mark.parametrize(
        "url",
        [
            "http://example.com/iniciar-sesión",
            "http://example.com/INICIAR-SESIÓN",
            "http://example.com/iniciar%20sesion",
            "http://example.com/iniciarsesion",
            "http://example.com/contraseña",
            "http://example.com/CONTRASEÑA",
            "http://example.com/cédula",
            "http://example.com/verificación",
            "http://example.com/autenticación",
            "http://example.com/datos-personales",
        ],
    )
    def test_detecta_espanol_con_tildes(self, url: str) -> None:
        result = evaluate_social_engineering_keywords(normalize(url))

        assert result.activated is True, url
        assert result.points == 15

    @pytest.mark.parametrize(
        "url",
        [
            "http://bancolombia-seguridad.example.com/",
            "http://paypal-soporte.example.com/",
            "http://nequi.example.com/pago",
            "http://example.com/transferencia/banco",
            "http://example.com/tarjeta?saldo=0",
            "http://example.com/passwords",
            "http://example.com/banking",
        ],
    )
    def test_detecta_terminos_financieros(self, url: str) -> None:
        result = evaluate_social_engineering_keywords(normalize(url))

        assert result.activated is True, url
        assert result.points == 15

    @pytest.mark.parametrize(
        "url",
        [
            "http://example.com/products",
            "https://docs.example.org/guide",
            "http://example.com/news/2026",
            "http://shopping.example.com/",
            "http://routes.example.com/",
            "http://guardian.example.com/",
            "http://pseudo.example.com/",
            "http://vertigo.example.com/",
            "http://iniciar.example.com/sesion",
        ],
    )
    def test_no_activa_sin_palabras_clave_ni_por_subcadenas(self, url: str) -> None:
        result = evaluate_social_engineering_keywords(normalize(url))

        assert result.activated is False, url
        assert result.points == 0

    def test_catalogo_organizado_por_categorias(self) -> None:
        assert set(SENSITIVE_KEYWORDS_BY_CATEGORY) == {
            "inicio_sesion",
            "credenciales",
            "verificacion_identidad",
            "seguridad_bloqueo",
            "urgencia_amenaza",
            "informacion_personal",
            "entidades_financieras",
        }
        assert all(categoria for categoria in SENSITIVE_KEYWORDS_BY_CATEGORY.values())
        union = frozenset().union(*SENSITIVE_KEYWORDS_BY_CATEGORY.values())
        assert SENSITIVE_KEYWORDS == union

    def test_catalogo_normalizado(self) -> None:
        for keyword in SENSITIVE_KEYWORDS:
            assert keyword == keyword.lower()
            assert normalize_text(keyword) == keyword

    @pytest.mark.parametrize(
        "keyword",
        [
            "iniciar-sesion",
            "contrasena",
            "cedula",
            "verificacion",
            "bancolombia",
            "paypal",
            "soporte",
            "datos-personales",
        ],
    )
    def test_catalogo_contiene_terminos_representativos(self, keyword: str) -> None:
        assert keyword in SENSITIVE_KEYWORDS

    def test_exact_match_es_subconjunto_del_catalogo(self) -> None:
        assert EXACT_MATCH_KEYWORDS <= SENSITIVE_KEYWORDS

    def test_es_pura_y_determinista(self) -> None:
        parsed = normalize("http://secure-login.example.com/")

        assert evaluate_social_engineering_keywords(parsed) == evaluate_social_engineering_keywords(
            parsed
        )
