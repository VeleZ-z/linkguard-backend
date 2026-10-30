"""Pruebas unitarias del cliente PhishTank con mocks estrictos (H3-T02).

Todas las peticiones se interceptan con ``respx``: no se abre ningún socket
real ni se contacta la URL analizada (RNF-101).
"""

from __future__ import annotations

import time

import httpx
import pytest
import respx
from app.cache.phishtank_cache import PhishtankCache
from app.clients.phishtank import USER_AGENT, PhishtankClient
from app.core.config import get_settings
from app.schemas import PhishtankStatus

API_URL = get_settings().PHISHTANK_API_URL
URL_ANALIZADA = "http://evil.example/login"


def _cliente(*, cache: PhishtankCache | None = None) -> PhishtankClient:
    return PhishtankClient(cache=cache or PhishtankCache(ttl_seconds=60))


class TestPhishtankClientExito:
    """Respuestas válidas de la API pública."""

    @respx.mock
    async def test_tc_rf_401_encontrada(self) -> None:
        ruta = respx.post(API_URL).mock(
            return_value=httpx.Response(
                200,
                json={"results": {"in_database": True, "valid": True}},
            )
        )

        result = await _cliente().check_url(URL_ANALIZADA)

        assert result.is_match is True
        assert result.status is PhishtankStatus.AVAILABLE
        assert ruta.called

    @respx.mock
    async def test_tc_rf_402_no_encontrada(self) -> None:
        respx.post(API_URL).mock(
            return_value=httpx.Response(
                200,
                json={"results": {"in_database": False, "valid": True}},
            )
        )

        result = await _cliente().check_url(URL_ANALIZADA)

        assert result.is_match is False
        assert result.status is PhishtankStatus.AVAILABLE

    @respx.mock
    async def test_registro_invalido_no_es_coincidencia(self) -> None:
        respx.post(API_URL).mock(
            return_value=httpx.Response(
                200,
                json={"results": {"in_database": True, "valid": False}},
            )
        )

        result = await _cliente().check_url(URL_ANALIZADA)

        assert result.is_match is False
        assert result.status is PhishtankStatus.AVAILABLE

    @respx.mock
    async def test_envia_url_y_formato_sin_claves(self) -> None:
        ruta = respx.post(API_URL).mock(
            return_value=httpx.Response(200, json={"results": {"in_database": False}})
        )

        await _cliente().check_url(URL_ANALIZADA)

        request = ruta.calls[0].request
        cuerpo = request.content.decode()
        assert "url=" in cuerpo
        assert "format=json" in cuerpo
        assert request.headers["User-Agent"] == USER_AGENT
        assert request.headers["User-Agent"] == "phishtank/linkguard-api-v1.0"
        assert "app_key" not in cuerpo


class TestPhishtankClientFallback:
    """Cualquier fallo degrada a un resultado neutro, nunca propaga."""

    @respx.mock
    async def test_tc_rf_403_timeout(self) -> None:
        respx.post(API_URL).mock(side_effect=httpx.ReadTimeout("agotado"))

        result = await _cliente().check_url(URL_ANALIZADA)

        assert result.is_match is False
        assert result.status is PhishtankStatus.TIMEOUT

    @respx.mock
    async def test_tc_rf_404_http_503(self) -> None:
        respx.post(API_URL).mock(return_value=httpx.Response(503))

        result = await _cliente().check_url(URL_ANALIZADA)

        assert result.is_match is False
        assert result.status is PhishtankStatus.UNAVAILABLE

    @respx.mock
    async def test_http_404(self) -> None:
        respx.post(API_URL).mock(return_value=httpx.Response(404))

        result = await _cliente().check_url(URL_ANALIZADA)

        assert result.status is PhishtankStatus.UNAVAILABLE

    @respx.mock
    async def test_json_invalido(self) -> None:
        respx.post(API_URL).mock(return_value=httpx.Response(200, content=b"<html>no json</html>"))

        result = await _cliente().check_url(URL_ANALIZADA)

        assert result.status is PhishtankStatus.UNAVAILABLE


class TestPhishtankClientCache:
    """La caché evita la segunda llamada de red (RF-403, TC-RF-405)."""

    @respx.mock
    async def test_tc_rf_405_segunda_consulta_desde_cache(self) -> None:
        ruta = respx.post(API_URL).mock(
            return_value=httpx.Response(
                200,
                json={"results": {"in_database": True, "valid": True}},
            )
        )
        cliente = _cliente()

        primera = await cliente.check_url(URL_ANALIZADA)
        inicio = time.perf_counter()
        segunda = await cliente.check_url(URL_ANALIZADA)
        transcurrido_ms = (time.perf_counter() - inicio) * 1000

        assert primera.status is PhishtankStatus.AVAILABLE
        assert segunda.status is PhishtankStatus.CACHED
        assert segunda.is_match is True
        assert ruta.call_count == 1
        assert transcurrido_ms < 1.0

    @respx.mock
    async def test_no_cachea_errores(self) -> None:
        ruta = respx.post(API_URL).mock(return_value=httpx.Response(503))
        cliente = _cliente()

        await cliente.check_url(URL_ANALIZADA)
        await cliente.check_url(URL_ANALIZADA)

        assert ruta.call_count == 2

    @respx.mock
    async def test_clave_de_cache_no_expone_la_url(self) -> None:
        clave = PhishtankClient.cache_key(URL_ANALIZADA)

        assert URL_ANALIZADA not in clave
        assert len(clave) == 64
        assert clave == PhishtankClient.cache_key(URL_ANALIZADA)
        assert clave != PhishtankClient.cache_key("http://otro.example/")


class TestAislamientoDeRed:
    """El cliente solo habla con el endpoint configurado (RNF-101)."""

    @respx.mock
    async def test_nunca_contacta_la_url_analizada(self) -> None:
        respx.post(API_URL).mock(
            return_value=httpx.Response(200, json={"results": {"in_database": False}})
        )
        # Si el cliente intentara contactar evil.example, respx lanzaría
        # AllMockedAssertionError por no existir una ruta registrada.
        result = await _cliente().check_url(URL_ANALIZADA)

        assert result.status is PhishtankStatus.AVAILABLE

    def test_timeout_configurado_por_defecto(self) -> None:
        cliente = _cliente()

        assert cliente._timeout == pytest.approx(get_settings().PHISHTANK_TIMEOUT)
        assert cliente._timeout == pytest.approx(4.0)


class TestPhishtankClientHelpers:
    """Parseo defensivo y singletons del cliente."""

    def test_rechaza_payload_no_dict(self) -> None:
        with pytest.raises(ValueError, match="formato inesperado"):
            PhishtankClient._is_match(["no", "es", "dict"])

    def test_rechaza_payload_sin_results(self) -> None:
        with pytest.raises(ValueError, match="results"):
            PhishtankClient._is_match({"meta": {"status": "ok"}})

    def test_configuracion_por_defecto(self) -> None:
        cliente = PhishtankClient(cache=PhishtankCache(ttl_seconds=60))

        assert cliente._api_url == API_URL
        assert cliente._timeout == pytest.approx(get_settings().PHISHTANK_TIMEOUT)

    def test_instancia_unica_y_reset(self) -> None:
        from app.clients.phishtank import (
            get_phishtank_client,
            reset_phishtank_client,
        )

        reset_phishtank_client()
        primera = get_phishtank_client()
        segunda = get_phishtank_client()
        assert primera is segunda

        reset_phishtank_client()
        assert get_phishtank_client() is not primera
