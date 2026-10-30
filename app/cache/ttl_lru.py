"""Caché LRU en memoria con expiración por TTL (RF-403, RNF-103).

La estructura vive únicamente en RAM: no escribe archivos ni usa servicios
externos. Es segura para un único ``event loop`` de asyncio y para llamadas
concurrentes desde hilos distintos gracias a un lock de grano grueso.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from typing import Final

#: Número máximo de entradas por defecto para acotar el consumo de RAM.
DEFAULT_MAX_ENTRIES: Final[int] = 1024


class TTLLRUCache[K, V]:
    """Caché clave-valor con política LRU y expiración temporal.

    Cada entrada se guarda junto al instante monotónico en que expira. Al
    superar ``max_entries`` se descarta la entrada usada menos recientemente.
    """

    def __init__(
        self,
        ttl_seconds: float,
        *,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Inicializa la caché con TTL y capacidad máxima.

        Args:
            ttl_seconds: Vida útil de cada entrada, en segundos.
            max_entries: Número máximo de entradas retenidas en RAM.
            clock: Fuente de tiempo monotónico inyectable para pruebas.

        Raises:
            ValueError: Si ``ttl_seconds`` o ``max_entries`` no son positivos.
        """
        if ttl_seconds <= 0:
            raise ValueError("El TTL debe ser mayor que cero")
        if max_entries < 1:
            raise ValueError("max_entries debe ser al menos 1")

        self._ttl = float(ttl_seconds)
        self._max_entries = max_entries
        self._clock = clock
        self._data: OrderedDict[K, tuple[float, V]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: K) -> V | None:
        """Devuelve el valor vigente o ``None`` si no existe o expiró."""
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None

            expires_at, value = entry
            if self._clock() >= expires_at:
                del self._data[key]
                return None

            self._data.move_to_end(key)
            return value

    def set(self, key: K, value: V) -> None:
        """Inserta o renueva una entrada y aplica la política LRU."""
        with self._lock:
            self._data[key] = (self._clock() + self._ttl, value)
            self._data.move_to_end(key)
            while len(self._data) > self._max_entries:
                self._data.popitem(last=False)

    def clear(self) -> None:
        """Vacía por completo la caché."""
        with self._lock:
            self._data.clear()

    def purge_expired(self) -> int:
        """Elimina las entradas expiradas y retorna cuántas se descartaron."""
        with self._lock:
            now = self._clock()
            expired = [key for key, (expires_at, _) in self._data.items() if now >= expires_at]
            for key in expired:
                del self._data[key]
            return len(expired)

    def __len__(self) -> int:
        """Número de entradas retenidas, incluidas las aún no purgadas."""
        with self._lock:
            return len(self._data)

    def __contains__(self, key: object) -> bool:
        """Indica si la clave existe y sigue vigente."""
        return self.get(key) is not None  # type: ignore[arg-type]


__all__ = ["DEFAULT_MAX_ENTRIES", "TTLLRUCache"]
