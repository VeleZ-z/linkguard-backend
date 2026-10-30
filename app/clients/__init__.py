"""Clientes de servicios externos usados por el backend."""

from __future__ import annotations

from app.clients.phishtank import (
    PhishtankClient,
    PhishtankResult,
    get_phishtank_client,
)

__all__ = [
    "PhishtankClient",
    "PhishtankResult",
    "get_phishtank_client",
]
