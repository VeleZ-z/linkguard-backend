"""Compatibilidad con la ruta ``app/config.py`` de la especificación.

La definición canónica de la configuración vive en :mod:`app.core.config`.
Este módulo reexporta los símbolos para que las referencias de la
especificación de estructura de directorios sigan funcionando.
"""

from __future__ import annotations

from app.core.config import Environment, Settings, get_settings

__all__ = ["Environment", "Settings", "get_settings"]
