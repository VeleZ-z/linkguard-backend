"""Modelos internos del motor de reglas léxicas (RF-301).

Define las estructuras de datos que fluyen por el pipeline de análisis:
``ParsedURL`` (resultado de la normalización sintáctica) y ``RuleResult``
(resultado de la ejecución de una regla léxica pura).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ParsedURL(BaseModel):
    """Resultado del descomposición sintáctica de una URL normalizada.

    Expone exactamente los seis componentes de `urllib.parse` más el host
    desglosado, el puerto y la URL normalizada completa.
    """

    scheme: str = Field(description="Esquema del protocolo (ej. 'http', 'https').")
    netloc: str = Field(description="Ubicación de red completa (host:puerto).")
    host: str = Field(description="Nombre de host o dirección IP sin puerto.")
    port: int | None = Field(default=None, description="Puerto TCP explícito, si está presente.")
    path: str = Field(default="", description="Camino del recurso en el servidor.")
    params: str = Field(default="", description="Parámetros de URL (tras ';').")
    query: str = Field(default="", description="Cadena de consulta (tras '?').")
    fragment: str = Field(default="", description="Fragmento (tras '#').")
    normalized_url: str = Field(description="URL completa tras la normalización sintáctica.")
    main_domain: str | None = Field(
        default=None,
        description="Dominio principal registrable (eTLD+1), si se pudo determinar.",
    )
    subdomains: list[str] = Field(
        default_factory=list,
        description="Etiquetas de subdominio previas al dominio principal.",
    )
    is_ip: bool = Field(
        default=False,
        description="Indica si el host es una dirección IP literal (IPv4 o IPv6).",
    )


class RuleResult(BaseModel):
    """Resultado de la evaluación de una única regla léxica pura."""

    rule_id: str = Field(description="Identificador de la regla (ej. 'F02_DIRECT_IP').")
    activated: bool = Field(description="Indica si la regla se activó sobre la URL.")
    points: int = Field(
        default=0,
        ge=0,
        description="Puntos aportados al puntaje de riesgo si se activó.",
    )
    title: str = Field(description="Título técnico legible de la anomalía.")
    description: str = Field(
        description="Explicación en español neutro comprensible para el usuario."
    )


__all__ = ["ParsedURL", "RuleResult"]
