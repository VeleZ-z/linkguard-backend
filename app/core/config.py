"""Configuración centralizada del servicio LinkGuard.

Todas las variables se leen desde el entorno del proceso o desde un archivo
``.env`` local (ver ``.env.example``). Ningún valor sensible se escribe en el
código fuente, en cumplimiento de la regla de manejo de secretos del proyecto.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

Environment = Literal["development", "testing", "production"]


class Settings(BaseSettings):
    """Parámetros de ejecución del backend, validados con Pydantic v2."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    ENVIRONMENT: Environment = Field(
        default="development",
        description="Entorno de ejecución del servicio.",
    )
    PORT: int = Field(
        default=8000,
        ge=1,
        le=65535,
        description="Puerto TCP de escucha del servicio.",
    )
    CORS_ORIGINS: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173"],
        description=(
            "Orígenes autorizados por CORS. Se acepta una lista separada por "
            "comas o un arreglo JSON."
        ),
    )
    PHISHTANK_TIMEOUT: float = Field(
        default=4.0,
        gt=0,
        le=30.0,
        description="Tiempo máximo de espera de PhishTank, en segundos (RF-402).",
    )
    PHISHTANK_TTL_SECONDS: int = Field(
        default=7200,
        gt=0,
        description="TTL de la caché LRU de PhishTank, en segundos (RF-403).",
    )
    RATE_LIMIT_PER_MINUTE: int = Field(
        default=30,
        gt=0,
        le=600,
        description="Límite de peticiones por minuto por dirección IP (RNF-105).",
    )
    PHISHTANK_API_URL: str = Field(
        default="https://checkurl.phishtank.com/checkurl/",
        description="Endpoint público de consulta de PhishTank.",
    )

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value: object) -> object:
        """Normaliza los orígenes CORS recibidos como texto desde el entorno."""
        if not isinstance(value, str):
            return value

        raw_value = value.strip()
        if not raw_value:
            return []
        if raw_value.startswith("["):
            return json.loads(raw_value)
        return [origin.strip() for origin in raw_value.split(",") if origin.strip()]

    @field_validator("PHISHTANK_API_URL")
    @classmethod
    def _validate_phishtank_url(cls, value: str) -> str:
        """Exige una URL HTTP(S) absoluta para el cliente de reputación."""
        if not value.startswith(("http://", "https://")):
            raise ValueError("PHISHTANK_API_URL debe ser una URL HTTP(S) absoluta")
        return value


@lru_cache
def get_settings() -> Settings:
    """Devuelve la instancia única de configuración del proceso."""
    return Settings()
