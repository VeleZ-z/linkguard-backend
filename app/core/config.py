"""Configuración centralizada del servicio LinkGuard.

Todas las variables se leen desde el entorno del proceso o desde un archivo
``.env`` local (ver ``.env.example``). Ningún valor sensible se escribe en el
código fuente, en cumplimiento de la regla de manejo de secretos del proyecto.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Annotated, Final, Literal
from urllib.parse import urlparse

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

Environment = Literal["development", "testing", "production"]

#: Único host autorizado para el endpoint de reputación (OBS-1).
#: La lista es explícita y exacta: no se aceptan subdominios ni sufijos, de
#: modo que ``checkurl.phishtank.com.evil.example`` queda rechazado.
PHISHTANK_ALLOWED_HOSTS: Final[frozenset[str]] = frozenset({"checkurl.phishtank.com"})


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

    @field_validator("CORS_ORIGINS")
    @classmethod
    def _validate_cors_origins(cls, value: list[str]) -> list[str]:
        """Rechaza comodines: el API nunca debe quedar abierto a todo origen.

        El origen efectivo se declara de forma explícita por entorno; un ``*``
        permitiría que cualquier sitio invoque la API con la credencial de la
        sesión del usuario final (RNF-104).
        """
        for origin in value:
            if "*" in origin:
                raise ValueError(
                    "CORS_ORIGINS no admite comodines; declare los orígenes "
                    "autorizados de forma explícita"
                )
        return value

    @field_validator("PHISHTANK_API_URL")
    @classmethod
    def _validate_phishtank_url(cls, value: str) -> str:
        """Exige una URL HTTP(S) absoluta, sin credenciales y con host permitido.

        Controles aplicados (OBS-1 y regla de secretos del proyecto):

        1. Esquema ``http`` o ``https`` con componente de red presente.
        2. Ausencia de usuario/contraseña embebidos: una URL de servicio con
           credenciales sería un secreto en la configuración.
        3. El host debe ser exactamente uno de ``PHISHTANK_ALLOWED_HOSTS``.
           Así una configuración errónea o manipulada no puede convertir al
           cliente de reputación en un vehículo hacia un destino arbitrario
           (defensa en profundidad frente a SSRF).

        El valor solo lo fija el despliegue (nunca el usuario final); por eso
        la allowlist no restringe la capacidad de análisis, sino el destino
        de la única petición saliente del servicio.
        """
        parsed = urlparse(value)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("PHISHTANK_API_URL debe ser una URL HTTP(S) absoluta")

        if parsed.username or parsed.password:
            raise ValueError("PHISHTANK_API_URL no debe incluir credenciales embebidas")

        host = (parsed.hostname or "").rstrip(".").lower()
        if host not in PHISHTANK_ALLOWED_HOSTS:
            raise ValueError(
                "PHISHTANK_API_URL debe apuntar a un host autorizado: "
                + ", ".join(sorted(PHISHTANK_ALLOWED_HOSTS))
            )
        return value


@lru_cache
def get_settings() -> Settings:
    """Devuelve la instancia única de configuración del proceso."""
    return Settings()
