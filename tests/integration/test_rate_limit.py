"""Pruebas del rate limiting por IP (base de H1-T13, TC-RNF-105).

Verifican que la petición 31 dentro de un minuto recibe HTTP 429 y que el
endpoint de salud no está sujeto al límite del análisis.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from app.core.rate_limit import limiter
from app.main import app

VALID_URL = "http://example.com/login-path"


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> None:
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client


async def test_peticion_31_es_rechazada(client: httpx.AsyncClient) -> None:
    """TC-RNF-105: 30 peticiones permitidas y la 31 recibe 429."""
    for _ in range(30):
        response = await client.post("/api/v1/analyze", json={"url": VALID_URL})
        assert response.status_code == 200

    response = await client.post("/api/v1/analyze", json={"url": VALID_URL})
    assert response.status_code == 429
    assert response.json() == {
        "error": {
            "code": "rate_limit_exceeded",
            "message": "Ha superado el límite de solicitudes permitidas por minuto",
        }
    }


async def test_health_no_esta_limitado(client: httpx.AsyncClient) -> None:
    for _ in range(30):
        assert (await client.post("/api/v1/analyze", json={"url": VALID_URL})).status_code == 200
    assert (await client.post("/api/v1/analyze", json={"url": VALID_URL})).status_code == 429

    health = await client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "healthy"
