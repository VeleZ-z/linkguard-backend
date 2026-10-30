"""Limitador de peticiones por dirección IP compartido (RNF-105).

Se define en un módulo propio para que ``app.main`` y el endpoint de análisis
usen exactamente la misma instancia de ``Limiter`` y, por tanto, el mismo
almacenamiento en memoria.

Resolución de la IP del cliente detrás de un proxy inverso (OBS-3)
------------------------------------------------------------------
El contenedor arranca Uvicorn con ``--proxy-headers`` y
``--forwarded-allow-ips`` (ver ``Dockerfile``). En ese modo, el middleware
``ProxyHeadersMiddleware`` de Uvicorn lee ``X-Forwarded-For`` **solo** de los
pares de confianza y reescribe ``scope["client"]``. Por eso
``request.client.host`` ya contiene la IP real del cliente y no la del proxy.

No se parsea ``X-Forwarded-For`` aquí a propósito: hacerlo en la aplicación
permitiría que cualquier cliente falsificara la cabecera y evadiera el límite
(una petición por IP inventada). La confianza en la cabecera queda delegada
al único componente que conoce la topología de red: el servidor ASGI. Si el
servicio se ejecuta sin ``--proxy-headers``, la clave es la IP del socket, es
decir, la del proxy, y el límite se aplicaría de forma global; por eso el
``Dockerfile`` fija las banderas y ``tests/integration/test_rate_limit.py``
cubre el comportamiento con ``ProxyHeadersMiddleware``.
"""

from __future__ import annotations

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def client_ip(request: Request) -> str:
    """Devuelve la IP del cliente resuelta por el servidor ASGI.

    Con ``--proxy-headers``, Uvicorn ya sustituyó ``scope["client"]`` por la
    dirección de ``X-Forwarded-For`` del proxy de confianza; sin esa bandera,
    es la IP del socket. En ambos casos es la única fuente fiable:
    ``request.client`` nunca es influenciable por cabeceras no validadas.
    """
    return get_remote_address(request)


#: Instancia única del limitador; la clave es la IP del cliente.
limiter = Limiter(key_func=client_ip)

__all__ = ["client_ip", "limiter"]
