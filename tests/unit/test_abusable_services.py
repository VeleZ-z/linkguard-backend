"""Pruebas de la regla de emparejamiento de servicios abusables (RF-503).

Cubre los casos de límite de etiqueta y prefijo de ruta especificados.
"""

from __future__ import annotations

from app.engine.data.abusable_services import _matches_abusable


class TestMatchesAbusable:
    """Reglas de emparejamiento de abusable_services."""

    def test_web_app_subdomain_matches(self) -> None:
        """x.web.app coincide con web.app (límite de etiqueta)."""
        assert _matches_abusable("x.web.app") is True

    def test_evil_web_app_no_match(self) -> None:
        """evilweb.app NO coincide con web.app (no hay punto separador)."""
        assert _matches_abusable("evilweb.app") is False

    def test_dropbox_s_abc_matches(self) -> None:
        """dropbox.com/s/abc coincide con dropbox.com/s/ (prefijo de ruta)."""
        assert _matches_abusable("dropbox.com/s/abc") is True

    def test_dropbox_pricing_no_match(self) -> None:
        """dropbox.com/pricing NO coincide con dropbox.com/s/."""
        assert _matches_abusable("dropbox.com/pricing") is False

    def test_web_app_exact_match(self) -> None:
        """web.app coincide exactamente con web.app."""
        assert _matches_abusable("web.app") is True

    def test_dropbox_com_in_allowlist_is_abusable(self) -> None:
        """dropbox.com (agregado por coincidencia con allowlist) es abusable."""
        assert _matches_abusable("dropbox.com") is True

    def test_www_dropbox_s_abc_matches(self) -> None:
        """www.dropbox.com/s/abc coincide con dropbox.com/s/ (prefijo de ruta)."""
        assert _matches_abusable("www.dropbox.com/s/abc") is True

    def test_linkedin_slink_matches(self) -> None:
        """linkedin.com/slink coincide con el patrón linkedin.com/slink."""
        assert _matches_abusable("linkedin.com/slink") is True

    def test_linkedin_in_alguien_no_match(self) -> None:
        """linkedin.com/in/alguien NO coincide con linkedin.com/slink."""
        assert _matches_abusable("linkedin.com/in/alguien") is False
