"""Pruebas de runtime de los artefactos de reputación (RF-502 a RF-506).

Verifica caché, verificación SHA-256, degradación por artefacto y señales de
reputación sin red (RNF-101) ni escrituras en disco (RNF-103).
"""

from __future__ import annotations

import hashlib
from array import array
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.engine.models import ParsedURL
from app.reputation import allowlist as allowlist_module
from app.reputation import blocklist as blocklist_module
from app.reputation import loader


class TestAllowlistRuntime:
    """Caché y coincidencia por dominio registrable de la allowlist."""

    def test_cache_evita_relectura(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setattr(allowlist_module, "ALLOWLIST_PATH", tmp_path / "inexistente.txt")
        monkeypatch.setattr(allowlist_module, "_allowlist", frozenset({"paypal.com"}))
        monkeypatch.setattr(allowlist_module, "_allowlist_count", 1)

        assert allowlist_module.load_allowlist() == 1
        assert allowlist_module.is_allowlisted("WWW.PAYPAL.COM.") is True
        assert allowlist_module.is_allowlisted("example.invalid") is False


class TestBlocklistRuntime:
    """Hash determinista, búsqueda binaria y caché de los blocklists."""

    def test_hash_canonical_y_lookup_con_cache(self, monkeypatch: pytest.MonkeyPatch) -> None:
        clave_url = "ejemplo.com/camino"
        clave_host = "ejemplo.com"
        esperado_url = int.from_bytes(
            hashlib.blake2b(clave_url.encode("utf-8"), digest_size=8).digest(), "big"
        )
        assert blocklist_module.hash_canonical(clave_url) == esperado_url

        monkeypatch.setattr(blocklist_module, "_URL_HASHES", array("Q", [esperado_url]))
        monkeypatch.setattr(
            blocklist_module,
            "_HOST_HASHES",
            array("Q", [blocklist_module.hash_canonical(clave_host)]),
        )

        assert blocklist_module.lookup_url("http://Ejemplo.COM/camino") is True
        assert blocklist_module.lookup_host("Ejemplo.COM.") is True
        assert blocklist_module.lookup_url("http://ejemplo.com/otro") is False


class TestLoaderRuntime:
    """Estados reales de carga y señales ante fallos de artefactos."""

    def test_estados_reales_con_artefactos_actuales(self) -> None:
        assert loader.get_load_status() == {
            "allowlist": "ok",
            "blocklist_urls": "ok",
            "blocklist_hosts": "ok",
        }

    def test_mismatch_degrada_solo_un_artefacto(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        esperado_mal = "0123456789abcdef" + "0" * 48
        monkeypatch.setattr(loader, "_sha256_of", lambda path: "a" * 64)
        monkeypatch.setattr(
            loader,
            "_manifest_sha256",
            lambda key: esperado_mal if key == "blocklist_urls" else "a" * 64,
        )
        monkeypatch.setattr(loader, "_loaded", False)
        monkeypatch.setattr(
            loader,
            "_load_status",
            {"allowlist": "missing", "blocklist_urls": "missing", "blocklist_hosts": "missing"},
        )

        with caplog.at_level("WARNING", logger="linkguard.reputation"):
            estado = loader.get_load_status()

        assert estado == {
            "allowlist": "ok",
            "blocklist_urls": "degraded",
            "blocklist_hosts": "ok",
        }
        assert "REPUTATION_ARTIFACT_INVALID" in caplog.text
        assert "aaaaaaaa" in caplog.text
        assert "01234567" in caplog.text

    def test_artefacto_faltante_marca_missing(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(loader, "ALLOWLIST_PATH", tmp_path / "allowlist_inexistente.txt")
        monkeypatch.setattr(loader, "_loaded", False)
        monkeypatch.setattr(
            loader,
            "_load_status",
            {"allowlist": "ok", "blocklist_urls": "ok", "blocklist_hosts": "ok"},
        )

        estado = loader.get_load_status()

        assert estado["allowlist"] == "missing"
        assert estado["blocklist_urls"] == "ok"
        assert estado["blocklist_hosts"] == "ok"

    def test_artefacto_sobredimensionado_degrada(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setitem(loader.MAX_ARTIFACT_BYTES, "allowlist", 1)
        monkeypatch.setattr(loader, "_loaded", False)
        monkeypatch.setattr(
            loader,
            "_load_status",
            {"allowlist": "missing", "blocklist_urls": "missing", "blocklist_hosts": "missing"},
        )

        with caplog.at_level("WARNING", logger="linkguard.reputation"):
            estado = loader.get_load_status()

        assert estado["allowlist"] == "degraded"
        assert "tamaño máximo" in caplog.text

    def test_senales_de_reputacion(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(loader, "_loaded", True)
        monkeypatch.setattr(
            loader,
            "_load_status",
            {"allowlist": "ok", "blocklist_urls": "ok", "blocklist_hosts": "ok"},
        )
        monkeypatch.setattr(loader, "lookup_url", lambda url: "login" in url)
        monkeypatch.setattr(loader, "lookup_host", lambda host: host == "www.paypal.com")

        parsed = ParsedURL(
            scheme="https",
            netloc="www.paypal.com",
            host="www.paypal.com",
            path="/login",
            normalized_url="https://www.paypal.com/login",
        )
        señales = loader.get_reputation(parsed)

        assert señales.allowlisted is True
        assert señales.feed_url is True
        assert señales.feed_host is True
        assert bool(señales) is True

        abusable = ParsedURL(
            scheme="https",
            netloc="dropbox.com",
            host="dropbox.com",
            path="/s/abc",
            normalized_url="https://dropbox.com/s/abc",
        )
        assert loader.get_reputation(abusable).abusable is True

    def test_sin_normalized_url_no_falla(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(loader, "_loaded", True)
        monkeypatch.setattr(
            loader,
            "_load_status",
            {
                "allowlist": "missing",
                "blocklist_urls": "missing",
                "blocklist_hosts": "missing",
            },
        )

        señales = loader.get_reputation(SimpleNamespace(host="example.com"))

        assert señales.allowlisted is False
        assert señales.abusable is False
        assert señales.feed_url is False
        assert señales.feed_host is False
        assert bool(señales) is False
