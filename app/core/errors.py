"""Errores de dominio estructurados de LinkGuard (RF-105).

Estas excepciones representan fallos de validación sintáctica de la entrada.
Todas se mapean a ``HTTP 400 Bad Request`` y exponen un código estable más un
mensaje en español neutro (es-419) apto para el cliente final.
"""

from __future__ import annotations

from typing import Any, ClassVar


class LinkGuardError(Exception):
    """Excepción base de los errores de dominio mapeables a HTTP 400."""

    status_code: ClassVar[int] = 400
    error_code: ClassVar[str] = "invalid_request"
    default_message: ClassVar[str] = "La solicitud no es válida."

    def __init__(self, message: str | None = None) -> None:
        """Inicializa el error con un mensaje opcional que reemplaza al default."""
        self.message: str = message or self.default_message
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        """Serializa el error al sobre de respuesta del contrato de API."""
        return {
            "error": {
                "code": self.error_code,
                "message": self.message,
            }
        }


class URLTooLongError(LinkGuardError):
    """La URL supera la longitud máxima procesable por el servicio (RF-105)."""

    error_code: ClassVar[str] = "url_too_long"
    default_message: ClassVar[str] = "URL excede la longitud máxima procesable (4096 caracteres)"


class InvalidURLError(LinkGuardError):
    """La entrada recibida no puede interpretarse como una URL válida (RF-101)."""

    error_code: ClassVar[str] = "invalid_url"
    default_message: ClassVar[str] = "La entrada no corresponde a un enlace válido"


__all__ = [
    "InvalidURLError",
    "LinkGuardError",
    "URLTooLongError",
]
