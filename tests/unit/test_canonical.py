"""Pruebas doradas de canonical_url_key (RF-502, RF-504).

Cubre: http/https, mayúsculas en host, puerto, consulta, barra final, punycode
(IDN) y combinaciones de ellos.
"""

from __future__ import annotations

from app.reputation.canonical import canonical_url_key


class TestCanonicalUrlKey:
    """Casos dorados de canonicalización de claves de URL."""

    def test_http_sin_path(self) -> None:
        assert canonical_url_key("http://Ejemplo.COM") == "ejemplo.com"

    def https_con_path_y_barra_final(self) -> None:
        assert canonical_url_key("https://Ejemplo.COM/path/") == "ejemplo.com/path"

    def con_consulta(self) -> None:
        assert canonical_url_key("http://ejemplo.com/path?q=1&x=2") == "ejemplo.com/path"

    def con_fragmento(self) -> None:
        assert canonical_url_key("http://ejemplo.com/path#seccion") == "ejemplo.com/path"

    def con_puerto(self) -> None:
        assert canonical_url_key("http://ejemplo.com:8080/path") == "ejemplo.com:8080/path"

    def con_puerto_y_barra_final(self) -> None:
        assert canonical_url_key("http://ejemplo.com:8080/") == "ejemplo.com:8080"

    def con_consulta_fragmento_y_barra(self) -> None:
        assert canonical_url_key("https://Ejemplo.COM/a/b/?q=1#frag") == "ejemplo.com/a/b"

    def punycode_idn(self) -> None:
        # xn--nodera-hra es el punycode de ノドera.jp (ejemplo ilustrativo)
        assert canonical_url_key("http://XN--NODERA-HRA.jp/") == "xn--nodera-hra.jp"

    def solo_host_sin_path(self) -> None:
        assert canonical_url_key("http://ejemplo.com") == "ejemplo.com"

    def vacio(self) -> None:
        assert canonical_url_key("") == ""

    def con_userinfo(self) -> None:
        # El userinfo (paypal.com) se descarta; queda el host real (evil.com/x)
        assert canonical_url_key("https://paypal.com@evil.com/x") == "evil.com/x"

    def con_puerto_defecto_443(self) -> None:
        assert canonical_url_key("https://ejemplo.com:443/path") == "ejemplo.com/path"

    def con_puerto_defecto_80(self) -> None:
        assert canonical_url_key("http://ejemplo.com:80/path") == "ejemplo.com/path"

    def con_mayusculas_y_punto_final(self) -> None:
        # El punto final del host se elimina (FQDN sin punto raíz)
        assert canonical_url_key("HTTP://EJEMPLO.COM./path") == "ejemplo.com/path"

    def clave_sin_www(self) -> None:
        # Canonicalización de www y sin www son claves distintas (no se normaliza www)
        assert canonical_url_key("http://www.ejemplo.com/") == "www.ejemplo.com"
        assert canonical_url_key("http://ejemplo.com/") == "ejemplo.com"
