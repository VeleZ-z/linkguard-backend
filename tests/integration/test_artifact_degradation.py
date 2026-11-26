"""TC-RF-506-01 de extremo a extremo: artefactos alterados sin HTTP 500 (RNF-107).

Se simulan digests divergentes para el modelo y para las blocklists. El cliente
ASGI no abre sockets (RNF-101) y PhishTank queda deshabilitado por configuración.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.main import app
from app.ml import model as model_mod
from app.ml.model import clear_model_cache
from app.reputation import loader

URL = "http://example.com/news"


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> None:
    """Evita que el contador de slowapi se filtre entre pruebas."""
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    """Cliente ASGI sin red real."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client


async def test_artefactos_alterados_devuelven_200(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un SHA divergente degrada el artefacto, nunca derriba la petición."""
    monkeypatch.setenv("PHISHTANK_ENABLED", "false")
    get_settings.cache_clear()
    monkeypatch.setattr(loader, "_loaded", False)
    monkeypatch.setattr(
        loader,
        "_load_status",
        {"allowlist": "missing", "blocklist_urls": "missing", "blocklist_hosts": "missing"},
    )
    monkeypatch.setattr(loader, "_manifest_sha256", lambda _key: "0" * 64)
    monkeypatch.setattr(model_mod, "_manifest_sha256", lambda: "0" * 64)
    clear_model_cache()

    respuesta = await client.post("/api/v1/analyze", json={"url": URL})

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["url_analyzed"] == URL
    assert cuerpo["risk_level"] in {"Bajo", "Medio", "Alto"}
    assert "internal_error" not in respuesta.text
