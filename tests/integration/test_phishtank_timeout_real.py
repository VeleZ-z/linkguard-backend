"""Verificación del timeout efectivo con transporte HTTP real (H3-T11, RF-402).

``respx`` sustituye el transporte de red, por lo que **no aplica el reloj de
timeout**: la prueba TC-RF-403 valida la ruta de degradación, pero no que el
timeout se cumpla realmente. Este módulo cierra esa brecha levantando un
servidor HTTP local lento (127.0.0.1, puerto efímero) y comprobando que el
cliente aborta al vencer ``PHISHTANK_TIMEOUT``.

No se contacta ninguna URL externa ni la URL analizada: el único socket es
loopback contra un doble local. Por eso la prueba es **opt-in** y no forma
parte de la ejecución por defecto de CI, que conserva la garantía de cero
tráfico saliente. Para habilitarla:

    LINKGUARD_TIMEOUT_NETWORK_TESTS=1 pytest tests/integration/test_phishtank_timeout_real.py
"""

from __future__ import annotations

import asyncio
import os
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from app.cache.phishtank_cache import PhishtankCache
from app.clients.phishtank import PhishtankClient
from app.schemas import PhishtankStatus

#: Retardo del doble local: superior al timeout probado (4.0 s).
DELAY_S = 6.0

#: Bandera que habilita la prueba (opt-in por hermeticidad de CI).
FLAG_ENV = "LINKGUARD_TIMEOUT_NETWORK_TESTS"

pytestmark = pytest.mark.skipif(
    os.environ.get(FLAG_ENV) != "1",
    reason=f"Requiere {FLAG_ENV}=1 (prueba con socket loopback)",
)


class _HandlerLento(BaseHTTPRequestHandler):
    """Servidor que tarda ``DELAY_S`` segundos en responder."""

    def do_POST(self) -> None:  # noqa: N802 - firma impuesta por BaseHTTPRequestHandler
        time.sleep(DELAY_S)
        cuerpo = b'{"results": {"in_database": false, "valid": true}}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def log_message(self, *args: object) -> None:
        """Silencia el log por defecto del servidor."""

    def handle_one_request(self) -> None:
        """Absorbe el cierre abrupto del socket al abortar por timeout."""
        try:
            super().handle_one_request()
        except (BrokenPipeError, ConnectionResetError):
            pass


@pytest.fixture
def servidor_lento() -> Iterator[str]:
    """Levanta el doble local en loopback y devuelve su URL."""
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), _HandlerLento)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    try:
        yield f"http://127.0.0.1:{servidor.server_address[1]}/checkurl/"
    finally:
        servidor.shutdown()
        hilo.join(timeout=5)


class TestTimeoutEfectivo:
    """El timeout configurado aborta la petición real, sin propagar excepciones."""

    async def test_timeout_de_4s_aborta_la_peticion(self, servidor_lento: str) -> None:
        cliente = PhishtankClient(
            timeout=4.0, api_url=servidor_lento, cache=PhishtankCache(ttl_seconds=60)
        )

        inicio = time.perf_counter()
        resultado = await cliente.check_url("http://ejemplo.local/login")
        transcurrido = time.perf_counter() - inicio

        assert resultado.status is PhishtankStatus.TIMEOUT
        assert resultado.is_match is False
        assert transcurrido < 4.6, f"la espera {transcurrido:.2f}s excede el timeout de 4.0 s"

    async def test_timeout_corto_aborta_mas_rapido(self, servidor_lento: str) -> None:
        cliente = PhishtankClient(
            timeout=0.5, api_url=servidor_lento, cache=PhishtankCache(ttl_seconds=60)
        )

        inicio = time.perf_counter()
        resultado = await cliente.check_url("http://ejemplo.local/login")
        transcurrido = time.perf_counter() - inicio

        assert resultado.status is PhishtankStatus.TIMEOUT
        assert transcurrido < 1.2, f"la espera {transcurrido:.2f}s excede el timeout de 0.5 s"


class TestConcurrencia:
    """El timeout no bloquea el event loop: las consultas corren en paralelo."""

    async def test_dos_consultas_en_paralelo(self, servidor_lento: str) -> None:
        cliente = PhishtankClient(
            timeout=1.0, api_url=servidor_lento, cache=PhishtankCache(ttl_seconds=60)
        )

        inicio = time.perf_counter()
        resultados = await asyncio.gather(
            cliente.check_url("http://ejemplo.local/a"),
            cliente.check_url("http://ejemplo.local/b"),
        )
        transcurrido = time.perf_counter() - inicio

        assert all(r.status is PhishtankStatus.TIMEOUT for r in resultados)
        # Si fueran secuenciales, serían 2 s; en paralelo rondan 1 s.
        assert transcurrido < 1.8, (
            f"las consultas no se ejecutaron en paralelo ({transcurrido:.2f}s)"
        )
