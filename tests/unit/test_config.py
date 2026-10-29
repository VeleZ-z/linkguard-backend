"""Pruebas unitarias de la configuración centralizada (app.core.config).

Cubre valores por defecto, validaciones de rango, parseo de CORS_ORIGINS
(CSV y JSON), validación de PHISHTANK_API_URL y el comportamiento cacheado
de ``get_settings``.
"""

from __future__ import annotations

import pytest
from app.core.config import Environment, Settings, get_settings
from pydantic import ValidationError


#: Limpia la caché de lru_cache entre pruebas que mutan el entorno.
@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    """Resetea la caché de ``get_settings`` antes y después de cada prueba."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class TestSettingsDefaults:
    """Valores por defecto de ``Settings``."""

    def test_defaults(self) -> None:
        settings = Settings()
        assert settings.ENVIRONMENT == "development"
        assert settings.PORT == 8000
        assert settings.CORS_ORIGINS == ["http://localhost:5173"]
        assert settings.PHISHTANK_TIMEOUT == 4.0
        assert settings.PHISHTANK_TTL_SECONDS == 7200
        assert settings.RATE_LIMIT_PER_MINUTE == 30
        assert settings.PHISHTANK_API_URL == "https://checkurl.phishtank.com/checkurl/"


class TestEnvironment:
    """Campo ENVIRONMENT (Literal restringido)."""

    @pytest.mark.parametrize("value", ["development", "testing", "production"])
    def test_valores_permitidos(self, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
        monkeypatch.setenv("ENVIRONMENT", value)
        assert Settings().ENVIRONMENT == value  # type: ignore[comparison-overlap]

    def test_valor_invalido_es_rechazado(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ENVIRONMENT", "produccion")
        with pytest.raises(ValidationError):
            Settings()


class TestPort:
    """Campo PORT (1..65535)."""

    def test_valor_por_defecto(self) -> None:
        assert Settings().PORT == 8000

    @pytest.mark.parametrize("value", ["1", "8080", "65535"])
    def test_rango_valido(self, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
        monkeypatch.setenv("PORT", value)
        assert Settings().PORT == int(value)

    @pytest.mark.parametrize("value", ["0", "65536", "abc", "-1"])
    def test_rango_invalido(self, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
        monkeypatch.setenv("PORT", value)
        with pytest.raises(ValidationError):
            Settings()


class TestCorsOrigins:
    """Campo CORS_ORIGINS (CSV, JSON o lista)."""

    def test_valor_por_defecto(self) -> None:
        assert Settings().CORS_ORIGINS == ["http://localhost:5173"]

    def test_csv_string(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CORS_ORIGINS", "http://a.local, https://b.local ")
        assert Settings().CORS_ORIGINS == ["http://a.local", "https://b.local"]

    def test_json_string(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CORS_ORIGINS", '["https://app.example.com"]')
        assert Settings().CORS_ORIGINS == ["https://app.example.com"]

    def test_texto_vacio_devuelve_lista_vacia(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CORS_ORIGINS", "")
        assert Settings().CORS_ORIGINS == []

    def test_lista_pasa_sin_transformar(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CORS_ORIGINS", '["https://x.local"]')
        assert Settings().CORS_ORIGINS == ["https://x.local"]


class TestPhishtankTimeout:
    """Campo PHISHTANK_TIMEOUT (>0, <=30)."""

    def test_valor_por_defecto(self) -> None:
        assert Settings().PHISHTANK_TIMEOUT == 4.0

    @pytest.mark.parametrize("value", ["0.1", "4", "30"])
    def test_rango_valido(self, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
        monkeypatch.setenv("PHISHTANK_TIMEOUT", value)
        assert Settings().PHISHTANK_TIMEOUT == float(value)

    @pytest.mark.parametrize("value", ["0", "-1", "30.1", "abc"])
    def test_rango_invalido(self, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
        monkeypatch.setenv("PHISHTANK_TIMEOUT", value)
        with pytest.raises(ValidationError):
            Settings()


class TestPhishtankTtlSeconds:
    """Campo PHISHTANK_TTL_SECONDS (>0)."""

    def test_valor_por_defecto(self) -> None:
        assert Settings().PHISHTANK_TTL_SECONDS == 7200

    @pytest.mark.parametrize("value", ["1", "3600"])
    def test_valor_valido(self, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
        monkeypatch.setenv("PHISHTANK_TTL_SECONDS", value)
        assert Settings().PHISHTANK_TTL_SECONDS == int(value)

    @pytest.mark.parametrize("value", ["0", "-1", "abc"])
    def test_valor_invalido(self, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
        monkeypatch.setenv("PHISHTANK_TTL_SECONDS", value)
        with pytest.raises(ValidationError):
            Settings()


class TestRateLimitPerMinute:
    """Campo RATE_LIMIT_PER_MINUTE (>0, <=600)."""

    def test_valor_por_defecto(self) -> None:
        assert Settings().RATE_LIMIT_PER_MINUTE == 30

    @pytest.mark.parametrize("value", ["1", "30", "600"])
    def test_valor_valido(self, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
        monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", value)
        assert Settings().RATE_LIMIT_PER_MINUTE == int(value)

    @pytest.mark.parametrize("value", ["0", "-1", "601", "abc"])
    def test_valor_invalido(self, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
        monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", value)
        with pytest.raises(ValidationError):
            Settings()


class TestPhishtankApiUrl:
    """Campo PHISHTANK_API_URL (debe ser http(s) absoluto)."""

    def test_valor_por_defecto(self) -> None:
        assert Settings().PHISHTANK_API_URL == "https://checkurl.phishtank.com/checkurl/"

    @pytest.mark.parametrize(
        "value",
        ["http://phishtank.local/check", "https://phishtank.local/check/"],
    )
    def test_url_valida(self, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
        monkeypatch.setenv("PHISHTANK_API_URL", value)
        assert Settings().PHISHTANK_API_URL == value

    @pytest.mark.parametrize(
        "value",
        ["ftp://phishtank.local", "not-a-url", "", "///relative"],
    )
    def test_url_invalida(self, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
        monkeypatch.setenv("PHISHTANK_API_URL", value)
        with pytest.raises(ValidationError):
            Settings()


class TestGetSettings:
    """Función cacheada ``get_settings``."""

    def test_devuelve_settings(self) -> None:
        settings = get_settings()
        assert isinstance(settings, Settings)

    def test_es_cacheado(self) -> None:
        """Misma instancia mientras no se limpie la caché."""
        assert get_settings() is get_settings()

    def test_respeta_cambios_de_entorno_despues_de_cache_clear(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PORT", "9000")
        get_settings.cache_clear()
        assert get_settings().PORT == 9000

    def test_env_tiene_prioridad_sobre_valor_por_defecto(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PORT", "3000")
        get_settings.cache_clear()
        assert get_settings().PORT == 3000


class TestEnvironmentType:
    """Alias ``Environment`` (Literal)."""

    @pytest.mark.parametrize("value", ["development", "testing", "production"])
    def test_valor_aceptado_por_settings(self, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
        monkeypatch.setenv("ENVIRONMENT", value)
        assert Settings().ENVIRONMENT == value  # type: ignore[comparison-overlap]

    def test_todos_los_valores_permitidos(self) -> None:
        valores: list[str] = ["development", "testing", "production"]
        assert list(__import__("typing").get_args(Environment)) == valores
