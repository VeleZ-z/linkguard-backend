"""Pruebas unitarias del normalizador sintáctico (H1-T07, RF-101 a RF-105).

Cubre los casos ``TC-RF-101``…``TC-RF-105`` y los bordes ``TC-EDGE-01``…``04``
del plan de pruebas, además del desglose de host (dominio principal,
subdominios, IP) y la garantía de aislamiento de red (RNF-101).
"""

from __future__ import annotations

import socket

import pytest
from app.core.errors import InvalidURLError, URLTooLongError
from app.engine.models import ParsedURL
from app.normalization import MAX_URL_LENGTH, normalize


class TestSanitizacionRF101:
    """TC-RF-101: stripping y eliminación de caracteres de control."""

    def test_strip_de_espacios_iniciales_y_finales(self) -> None:
        parsed = normalize("  http://example.com/demo  ")
        assert parsed.normalized_url == "http://example.com/demo"

    def test_elimina_caracteres_de_control_internos(self) -> None:
        parsed = normalize("http://exam\x00ple.com/pa\x1fth\x7f")
        assert parsed.host == "example.com"
        assert parsed.path == "/path"
        assert parsed.normalized_url == "http://example.com/path"

    def test_elimina_controles_y_espacios_en_los_extremos(self) -> None:
        parsed = normalize("\x00\n  http://example.com/demo \x1f\x7f")
        assert parsed.normalized_url == "http://example.com/demo"

    def test_no_deja_controles_en_ningun_componente(self) -> None:
        parsed = normalize("http://example.com/a\x01b?q=\x02x#f\x03")
        assert "\x01" not in parsed.path
        assert "\x02" not in parsed.query
        assert "\x03" not in parsed.fragment


class TestInyeccionEsquemaRF102:
    """TC-RF-102: anteposición de ``http://`` cuando falta esquema."""

    def test_antepone_http_por_defecto(self) -> None:
        parsed = normalize("example.com/login-path")
        assert parsed.scheme == "http"
        assert parsed.normalized_url == "http://example.com/login-path"

    def test_respeta_esquema_https_explicito(self) -> None:
        parsed = normalize("https://example.com/login-path")
        assert parsed.scheme == "https"
        assert parsed.normalized_url == "https://example.com/login-path"

    def test_no_confunde_puerto_con_esquema(self) -> None:
        parsed = normalize("example.com:8080/login")
        assert parsed.scheme == "http"
        assert parsed.port == 8080
        assert parsed.normalized_url == "http://example.com:8080/login"


class TestParsingAtomicoRF103:
    """TC-RF-103: descomposición en los seis componentes de ``urllib.parse``."""

    def test_seis_componentes(self) -> None:
        parsed = normalize("https://example.com:8443/path;params?q=1#frag")
        assert parsed.scheme == "https"
        assert parsed.netloc == "example.com:8443"
        assert parsed.path == "/path"
        assert parsed.params == "params"
        assert parsed.query == "q=1"
        assert parsed.fragment == "frag"

    def test_componentes_opcionales_vacios(self) -> None:
        parsed = normalize("http://example.com")
        assert parsed.path == ""
        assert parsed.params == ""
        assert parsed.query == ""
        assert parsed.fragment == ""
        assert parsed.port is None

    def test_devuelve_parsed_url(self) -> None:
        assert isinstance(normalize("http://example.com"), ParsedURL)


class TestDecodificacionRF104:
    """TC-RF-104: percent-decoding e IDN→Punycode."""

    def test_decodifica_percent_en_path(self) -> None:
        parsed = normalize("http://example.com/%7Euser/index.html")
        assert parsed.path == "/~user/index.html"

    def test_decodifica_percent_en_query(self) -> None:
        parsed = normalize("http://example.com/buscar?q=a%20b")
        assert parsed.query == "q=a b"

    def test_convierte_idn_a_punycode(self) -> None:
        parsed = normalize("münchen.de")
        assert parsed.host == "xn--mnchen-3ya.de"
        assert parsed.host.startswith("xn--")
        assert parsed.normalized_url == "http://xn--mnchen-3ya.de"

    def test_idn_con_subdominio(self) -> None:
        parsed = normalize("http://www.münchen.de/straße")
        assert parsed.host == "www.xn--mnchen-3ya.de"
        assert parsed.main_domain == "xn--mnchen-3ya.de"
        assert parsed.subdomains == ["www"]


class TestLongitudRF105:
    """TC-RF-105: rechazo de cadenas por encima de 4096 caracteres."""

    def test_rechaza_4097_caracteres(self) -> None:
        with pytest.raises(URLTooLongError, match="longitud máxima procesable"):
            normalize("a" * (MAX_URL_LENGTH + 1))

    def test_acepta_exactamente_4096_caracteres(self) -> None:
        prefix = "http://example.com/"
        padded = prefix + "a" * (MAX_URL_LENGTH - len(prefix))
        assert len(padded) == MAX_URL_LENGTH
        parsed = normalize(padded)
        assert len(parsed.normalized_url) == MAX_URL_LENGTH

    def test_rechaza_una_url_valida_con_un_caracter_extra(self) -> None:
        prefix = "http://example.com/"
        padded = prefix + "a" * (MAX_URL_LENGTH - len(prefix) + 1)
        with pytest.raises(URLTooLongError):
            normalize(padded)


class TestCasosBorde:
    """TC-EDGE-01…04: entradas que deben lanzar ``InvalidURLError``."""

    def test_edge_01_texto_plano(self) -> None:
        with pytest.raises(InvalidURLError, match="enlace válido"):
            normalize("hola mundo este no es un link")

    @pytest.mark.parametrize("raw", ["", "   ", "\x00\x1f\x7f", "\n\t "])
    def test_edge_02_entrada_vacia_o_solo_espacios(self, raw: str) -> None:
        with pytest.raises(InvalidURLError):
            normalize(raw)

    @pytest.mark.parametrize(
        "raw",
        ["ftp://example.com/file", "javascript://alert", "file:///etc/passwd"],
    )
    def test_edge_03_esquemas_no_permitidos(self, raw: str) -> None:
        with pytest.raises(InvalidURLError):
            normalize(raw)

    @pytest.mark.parametrize(
        "raw",
        [
            "http://example.com:99999/",
            "http://example.com:abc/",
            "http://example.com:-1/",
        ],
    )
    def test_edge_04_puertos_invalidos(self, raw: str) -> None:
        with pytest.raises(InvalidURLError):
            normalize(raw)

    @pytest.mark.parametrize(
        "raw",
        [
            "http://",
            "http:///solo-path",
            "http://./",
            "http://" + "a" * 64 + ".com/",
            "http://exa%mple.com/",
        ],
    )
    def test_host_invalido(self, raw: str) -> None:
        with pytest.raises(InvalidURLError):
            normalize(raw)


class TestDesgloseDeHost:
    """Extracción de host, puerto, dominio principal, subdominios e IP."""

    def test_ipv4_literal(self) -> None:
        parsed = normalize("192.168.1.1/admin")
        assert parsed.is_ip is True
        assert parsed.host == "192.168.1.1"
        assert parsed.main_domain is None
        assert parsed.subdomains == []

    def test_ipv6_conserva_corchetes_en_netloc(self) -> None:
        parsed = normalize("http://[::1]:8080/x")
        assert parsed.is_ip is True
        assert parsed.host == "::1"
        assert parsed.netloc == "[::1]:8080"
        assert parsed.normalized_url == "http://[::1]:8080/x"

    def test_dominio_principal_y_subdominios(self) -> None:
        parsed = normalize("http://a.b.example.co.uk/x")
        assert parsed.main_domain == "example.co.uk"
        assert parsed.subdomains == ["a", "b"]

    def test_dominio_sin_subdominios(self) -> None:
        parsed = normalize("http://example.com/")
        assert parsed.main_domain == "example.com"
        assert parsed.subdomains == []

    def test_conserva_userinfo(self) -> None:
        parsed = normalize("http://user:pass@example.com/x")
        assert parsed.netloc == "user:pass@example.com"
        assert parsed.host == "example.com"

    def test_multiples_arroba_no_rompe_el_analisis(self) -> None:
        parsed = normalize("http://a@b@example.com/x")
        assert parsed.host == "example.com"
        assert "@" in parsed.normalized_url

    def test_normaliza_mayusculas(self) -> None:
        parsed = normalize("HTTP://EXAMPLE.COM/Path")
        assert parsed.scheme == "http"
        assert parsed.host == "example.com"
        assert parsed.normalized_url == "http://example.com/Path"

    def test_elimina_punto_final_del_host(self) -> None:
        parsed = normalize("http://example.com./x")
        assert parsed.host == "example.com"


class TestAislamientoDeRed:
    """RNF-101: la normalización nunca abre conexiones de red."""

    def test_no_usa_sockets(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _prohibido(*args: object, **kwargs: object) -> None:
            raise AssertionError("El normalizador no debe abrir conexiones de red")

        monkeypatch.setattr(socket, "socket", _prohibido)
        monkeypatch.setattr(socket, "create_connection", _prohibido)

        parsed = normalize("https://example.com/login?q=1")
        assert parsed.normalized_url == "https://example.com/login?q=1"

    def test_es_determinista(self) -> None:
        raw = "http://Sub.Example.com/a%7Eb?q=1#f"
        assert normalize(raw) == normalize(raw)
