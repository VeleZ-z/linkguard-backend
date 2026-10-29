"""Logging estructurado en JSON con anonimización de datos sensibles (H1-T10).

Todos los eventos se escriben a ``stdout`` como una línea JSON. La URL y la IP
del cliente **nunca** se registran en claro: se aplica SHA-256 y se publican
únicamente ``url_hash_sha256`` y ``client_ip_hash``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any, Final

#: Nombre del logger raíz del servicio.
LOGGER_NAME: Final[str] = "linkguard"

#: Atributos estándar de ``LogRecord`` que no deben duplicarse en el JSON.
_RESERVED_ATTRS: Final[frozenset[str]] = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }
)


class JsonFormatter(logging.Formatter):
    """Serializa cada registro como una línea JSON autocontenida."""

    def format(self, record: logging.LogRecord) -> str:
        """Convierte un ``LogRecord`` en un objeto JSON con sus campos extra."""
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED_ATTRS and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: int = logging.INFO) -> logging.Logger:
    """Configura el logger del servicio con salida JSON a ``stdout``.

    Es idempotente: llamarlo varias veces no duplica handlers.
    """
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)
    logger.propagate = False
    if not any(getattr(handler, "_linkguard_json", False) for handler in logger.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        handler._linkguard_json = True  # type: ignore[attr-defined]
        logger.addHandler(handler)
    return logger


def get_logger() -> logging.Logger:
    """Devuelve el logger del servicio, configurándolo si aún no existe."""
    logger = logging.getLogger(LOGGER_NAME)
    if not logger.handlers:
        return configure_logging()
    return logger


def hash_sensitive(value: str) -> str:
    """Devuelve el SHA-256 hexadecimal de un dato sensible (URL o IP)."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def log_analyze_event(
    *,
    url: str,
    client_ip: str | None,
    score: int,
    risk_level: str,
    phishtank_status: str,
    rules_activated_count: int,
    execution_time_ms: float,
) -> dict[str, Any]:
    """Emite el evento ``ANALYZE_EVENT`` con la URL y la IP anonimizadas.

    Returns:
        El diccionario del evento emitido (útil para pruebas y trazabilidad).
    """
    event: dict[str, Any] = {
        "event_type": "ANALYZE_EVENT",
        "url_hash_sha256": hash_sensitive(url),
        "client_ip_hash": hash_sensitive(client_ip or ""),
        "score": score,
        "risk_level": risk_level,
        "phishtank_status": phishtank_status,
        "rules_activated_count": rules_activated_count,
        "execution_time_ms": round(execution_time_ms, 2),
    }
    get_logger().info("ANALYZE_EVENT", extra=event)
    return event


__all__ = [
    "LOGGER_NAME",
    "JsonFormatter",
    "configure_logging",
    "get_logger",
    "hash_sensitive",
    "log_analyze_event",
]
