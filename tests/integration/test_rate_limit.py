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
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

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


class TestIpRealDetrasDeProxy:
    """OBS-3: con ``--proxy-headers`` el límite se aplica por cliente real.

    Se envuelve la app con el mismo middleware que activa Uvicorn con
    ``--proxy-headers``; ``ASGITransport(client=...)`` simula el proxy. Sin
    esa bandera, ``request.client.host`` sería la IP del proxy y las 30
    peticiones serían un único cubo compartido por todos los usuarios.
    """

    IP_PROXY = "10.0.0.1"

    @pytest.fixture
    async def proxy_client(self) -> AsyncIterator[httpx.AsyncClient]:
        proxy_app = ProxyHeadersMiddleware(app, trusted_hosts="*")
        transport = httpx.ASGITransport(app=proxy_app, client=(self.IP_PROXY, 12345))
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as http_client:
            yield http_client

    async def test_cada_ip_reenviada_tiene_su_propio_limite(
        self, proxy_client: httpx.AsyncClient
    ) -> None:
        # 20 + 20 supera el umbral de 30: si la clave fuera la IP del proxy,
        # la petición 31 recibiría 429.
        for indice in range(20):
            respuesta = await proxy_client.post(
                "/api/v1/analyze",
                json={"url": VALID_URL},
                headers={"X-Forwarded-For": "203.0.113.7"},
            )
            assert respuesta.status_code == 200, indice

        for indice in range(20):
            respuesta = await proxy_client.post(
                "/api/v1/analyze",
                json={"url": VALID_URL},
                headers={"X-Forwarded-For": "198.51.100.42"},
            )
            assert respuesta.status_code == 200, indice

    async def test_la_ip_reenviada_agota_su_propio_cubo(
        self, proxy_client: httpx.AsyncClient
    ) -> None:
        for _ in range(30):
            respuesta = await proxy_client.post(
                "/api/v1/analyze",
                json={"url": VALID_URL},
                headers={"X-Forwarded-For": "203.0.113.7"},
            )
            assert respuesta.status_code == 200

        agotada = await proxy_client.post(
            "/api/v1/analyze",
            json={"url": VALID_URL},
            headers={"X-Forwarded-For": "203.0.113.7"},
        )
        assert agotada.status_code == 429

        otra_ip = await proxy_client.post(
            "/api/v1/analyze",
            json={"url": VALID_URL},
            headers={"X-Forwarded-For": "198.51.100.42"},
        )
        assert otra_ip.status_code == 200
