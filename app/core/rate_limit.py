"""Limitador de peticiones por dirección IP compartido (RNF-105).

Se define en un módulo propio para que ``app.main`` y el endpoint de análisis
usen exactamente la misma instancia de ``Limiter`` y, por tanto, el mismo
almacenamiento en memoria.
"""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

#: Instancia única del limitador; la clave es la IP del cliente.
limiter = Limiter(key_func=get_remote_address)

__all__ = ["limiter"]
