"""Pruebas unitarias de los errores estructurados de dominio (H1-T05, RF-105).

Verifica el contrato de ``LinkGuardError`` como excepción base mapeable a
``HTTP 400`` y los mensajes por defecto en español neutro (es-419) de
``URLTooLongError`` e ``InvalidURLError``.
"""

from __future__ import annotations

import pytest
from app.core.errors import InvalidURLError, LinkGuardError, URLTooLongError


class TestLinkGuardError:
    """Contrato de la excepción base de dominio."""

    def test_status_code_es_400(self) -> None:
        assert LinkGuardError.status_code == 400

    def test_codigo_de_error_por_defecto(self) -> None:
        assert LinkGuardError.error_code == "invalid_request"

    def test_mensaje_por_defecto(self) -> None:
        error = LinkGuardError()
        assert error.message == "La solicitud no es válida."
        assert str(error) == "La solicitud no es válida."

    def test_mensaje_personalizado_reemplaza_al_default(self) -> None:
        error = LinkGuardError("Mensaje específico")
        assert error.message == "Mensaje específico"
        assert str(error) == "Mensaje específico"

    def test_to_dict_expone_el_sobre_error(self) -> None:
        error = LinkGuardError("Entrada inválida")
        assert error.to_dict() == {
            "error": {
                "code": "invalid_request",
                "message": "Entrada inválida",
            }
        }

    def test_to_dict_no_filtra_detalles_internos(self) -> None:
        """El sobre solo contiene ``code`` y ``message`` (sin trazas ni campos extra)."""
        payload = LinkGuardError().to_dict()
        assert set(payload) == {"error"}
        assert set(payload["error"]) == {"code", "message"}

    def test_es_una_excepcion_de_python(self) -> None:
        assert issubclass(LinkGuardError, Exception)
        with pytest.raises(LinkGuardError):
            raise LinkGuardError()


class TestURLTooLongError:
    """Error de longitud excesiva (RF-105)."""

    def test_hereda_de_linkguard_error(self) -> None:
        assert issubclass(URLTooLongError, LinkGuardError)

    def test_status_code_es_400(self) -> None:
        assert URLTooLongError.status_code == 400

    def test_mensaje_exacto_en_es_419(self) -> None:
        error = URLTooLongError()
        assert error.message == "URL excede la longitud máxima procesable (4096 caracteres)"

    def test_codigo_de_error_estable(self) -> None:
        assert URLTooLongError().to_dict() == {
            "error": {
                "code": "url_too_long",
                "message": "URL excede la longitud máxima procesable (4096 caracteres)",
            }
        }

    def test_se_puede_lanzar_y_capturar(self) -> None:
        with pytest.raises(URLTooLongError, match="longitud máxima procesable"):
            raise URLTooLongError()


class TestInvalidURLError:
    """Error de entrada no interpretable como enlace (RF-101)."""

    def test_hereda_de_linkguard_error(self) -> None:
        assert issubclass(InvalidURLError, LinkGuardError)

    def test_status_code_es_400(self) -> None:
        assert InvalidURLError.status_code == 400

    def test_mensaje_exacto_en_es_419(self) -> None:
        error = InvalidURLError()
        assert error.message == "La entrada no corresponde a un enlace válido"

    def test_codigo_de_error_estable(self) -> None:
        assert InvalidURLError().to_dict() == {
            "error": {
                "code": "invalid_url",
                "message": "La entrada no corresponde a un enlace válido",
            }
        }

    def test_se_puede_lanzar_y_capturar(self) -> None:
        with pytest.raises(InvalidURLError, match="enlace válido"):
            raise InvalidURLError()
