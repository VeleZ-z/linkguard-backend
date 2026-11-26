"""Pruebas de integración de variantes de PhishTank (H5-T13, RF-801/RF-802).

Todas las respuestas se interceptan con ``respx``: el cliente solo alcanza el
endpoint autorizado y jamás se abre tráfico contra la URL analizada (RNF-101).
El script opt-in se comprueba con su interruptor desactivado, sin red.
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib
import json
import time
from collections.abc import Iterator
from typing import Final
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx
from app.cache.phishtank_cache import PhishtankCache, reset_phishtank_cache
from app.clients.phishtank import (
    MAX_VARIANTS,
    VARIANT_LABELS,
    PhishtankClient,
    reset_phishtank_client,
)
from app.core.config import get_settings
from app.schemas import PhishtankStatus

API_URL: Final[str] = get_settings().PHISHTANK_API_URL
URL_ANALIZADA: Final[str] = "https://ejemplo.invalid/login"


@pytest.fixture(autouse=True)
def _cache_aislada() -> Iterator[None]:
    """Reinicia los singletones de caché y cliente antes y después de cada prueba."""

    reset_phishtank_cache()
    reset_phishtank_client()
    yield
    reset_phishtank_cache()
    reset_phishtank_client()


@pytest.fixture
def _ajustes_aislados(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Descarta la caché de ``get_settings`` tras modificar variables de entorno."""

    yield
    # ``monkeypatch`` restaura el entorno al finalizar; limpiar aquí evita
    # conservar la configuración de prueba en el objeto cacheado.
    get_settings.cache_clear()


def _cliente(
    *, timeout: float | None = None, cache: PhishtankCache | None = None
) -> PhishtankClient:
    """Construye un cliente con caché propia, sin compartir estado entre pruebas."""

    return PhishtankClient(
        timeout=timeout,
        cache=cache if cache is not None else PhishtankCache(ttl_seconds=60),
    )


def _url_del_cuerpo(request: httpx.Request) -> str:
    """Extrae el campo ``url`` del cuerpo form-urlencoded de la petición."""

    return parse_qs(request.content.decode())["url"][0]


def _respuesta_con_barra_final(request: httpx.Request) -> httpx.Response:
    """Solo reporta la variante terminada en ``/`` como phishing validado."""

    encontrado = _url_del_cuerpo(request).endswith("/")
    return httpx.Response(200, json={"results": {"in_database": encontrado, "valid": True}})


def _respuesta_no_encontrada(_request: httpx.Request) -> httpx.Response:
    """Respuesta neutra y definitiva para cualquier variante consultada."""

    return httpx.Response(200, json={"results": {"in_database": False, "valid": True}})


class TestVariantesRF801:
    """Las representaciones normativas se prueban en orden y sin duplicados."""

    @respx.mock
    async def test_tc_rf_801_01_solo_coincide_la_variante_con_barra_final(self) -> None:
        """Con `/login` hay dos variantes únicas: índice 0 y 1 (con barra).

        ``build_variants`` devuelve cuatro entradas, pero las tres primeras son
        idénticas. ``check_url`` deduplica, descarta el negativo de ``/login`` y
        alcanza la variante con barra final en la misma invocación (RF-801).
        """

        ruta = respx.post(API_URL).mock(side_effect=_respuesta_con_barra_final)
        cliente = _cliente()

        resultado = await cliente.check_url(URL_ANALIZADA)

        assert resultado.is_match is True
        assert resultado.status is PhishtankStatus.AVAILABLE
        assert resultado.variant_index == 1
        assert ruta.call_count == 2
        assert [_url_del_cuerpo(llamada.request) for llamada in ruta.calls] == [
            URL_ANALIZADA,
            f"{URL_ANALIZADA}/",
        ]
        # Ninguna petición al host analizado: solo se alcanza el endpoint autorizado.
        host_autorizado = urlparse(API_URL).hostname
        assert all(llamada.request.url.host == host_autorizado for llamada in ruta.calls)

    def test_variantes_orden_y_dedup(self) -> None:
        """Cuatro variantes ordenadas, con saneamiento y normalización visibles."""

        variantes = PhishtankClient.build_variants("  HTTPS://Ejemplo.INVALID/ruta  ")

        assert len(variantes) == MAX_VARIANTS == 4
        assert VARIANT_LABELS == (
            "original_saneada",
            "normalizada",
            "sin_barra_final",
            "con_barra_final",
        )
        assert variantes[0] == "HTTPS://Ejemplo.INVALID/ruta"
        assert " " not in variantes[0]
        assert variantes[1] == "https://ejemplo.invalid/ruta"
        assert variantes[2] == variantes[1]
        assert variantes[3] == f"{variantes[2]}/"

    @respx.mock
    async def test_check_url_no_consulta_variantes_duplicadas(self) -> None:
        """Con tres variantes iguales, solo se envían dos peticiones HTTP.

        La negativa de ``/login`` no detiene la búsqueda (RF-801): se consulta
        ``/login/`` y, al no encontrar coincidencia, se reporta ``available``.
        La segunda invocación lee ambas variantes desde caché.
        """

        ruta = respx.post(API_URL).mock(side_effect=_respuesta_no_encontrada)
        cliente = _cliente()

        primero = await cliente.check_url(URL_ANALIZADA)
        segundo = await cliente.check_url(URL_ANALIZADA)

        assert primero.status is PhishtankStatus.AVAILABLE
        assert segundo.status is PhishtankStatus.CACHED
        assert segundo.is_match is False
        assert ruta.call_count == 2
        assert [_url_del_cuerpo(llamada.request) for llamada in ruta.calls] == [
            URL_ANALIZADA,
            f"{URL_ANALIZADA}/",
        ]


class TestConfiguracionYCache:
    """Clave opcional por entorno y caché por hash de cada variante."""

    @respx.mock
    async def test_app_key_opcional_por_entorno(
        self, monkeypatch: pytest.MonkeyPatch, _ajustes_aislados: None
    ) -> None:
        """La clave se envía como campo del cuerpo solo si está definida."""

        ruta = respx.post(API_URL).mock(side_effect=_respuesta_no_encontrada)

        monkeypatch.setenv("PHISHTANK_APP_KEY", "clave-de-prueba")
        get_settings.cache_clear()
        await _cliente().check_url(URL_ANALIZADA)
        cuerpo_con_clave = ruta.calls[-1].request.content.decode()
        assert parse_qs(cuerpo_con_clave)["app_key"] == ["clave-de-prueba"]

        monkeypatch.setenv("PHISHTANK_APP_KEY", "")
        get_settings.cache_clear()
        await _cliente().check_url(URL_ANALIZADA)
        cuerpo_sin_clave = ruta.calls[-1].request.content.decode()
        assert "app_key" not in parse_qs(cuerpo_sin_clave)

    @respx.mock
    async def test_cache_por_variante_sha256(self) -> None:
        """Una variante cacheada no vuelve a generar petición HTTP."""

        ruta = respx.post(API_URL).mock(side_effect=_respuesta_no_encontrada)
        cache = PhishtankCache(ttl_seconds=60)
        cliente = _cliente(cache=cache)
        url_con_barra = f"{URL_ANALIZADA}/"

        primera = await cliente.check_url(URL_ANALIZADA)
        intermedia = await cliente.check_url(url_con_barra)
        peticiones_previas = ruta.call_count
        segunda = await cliente.check_url(url_con_barra)

        assert primera.status is PhishtankStatus.AVAILABLE
        assert intermedia.status is PhishtankStatus.CACHED
        assert segunda.status is PhishtankStatus.CACHED
        assert ruta.call_count == peticiones_previas == 2
        assert len({_url_del_cuerpo(llamada.request) for llamada in ruta.calls}) == 2

        for variante in PhishtankClient.build_variants(URL_ANALIZADA):
            clave = PhishtankClient.cache_key(variante)
            assert clave == hashlib.sha256(variante.encode("utf-8")).hexdigest()
            assert len(clave) == 64
        assert PhishtankClient.cache_key(URL_ANALIZADA) != PhishtankClient.cache_key(url_con_barra)


class TestPresupuestoYDegradacion:
    """Timeout global, 5xx y verificador opt-in sin tráfico real."""

    @respx.mock
    async def test_presupuesto_global_de_timeout(self) -> None:
        """Varios timeouts agotan el plazo y devuelven 200 status=timeout."""

        ruta = respx.post(API_URL).mock(side_effect=httpx.ReadTimeout("tiempo agotado"))

        inicio = time.perf_counter()
        resultado = await _cliente(timeout=0.15).check_url(URL_ANALIZADA)
        transcurrido = time.perf_counter() - inicio

        assert resultado.status is PhishtankStatus.TIMEOUT
        assert resultado.is_match is False
        assert resultado.is_unverified is False
        # El presupuesto es global: no se suman 4 × 0.15 s ni 4 × 4.0 s.
        assert transcurrido < 1.0
        assert 1 <= ruta.call_count <= MAX_VARIANTS

    @respx.mock
    async def test_503_permanece_unavailable(self) -> None:
        """Un 5xx detiene las variantes para no agravar el límite de tasa."""

        ruta = respx.post(API_URL).mock(return_value=httpx.Response(503))

        resultado = await _cliente().check_url(URL_ANALIZADA)

        assert resultado.status is PhishtankStatus.UNAVAILABLE
        assert resultado.is_match is False
        assert ruta.call_count == 1

    def test_script_live_omite_sin_autorizacion(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Sin ``LINKGUARD_LIVE_TESTS=1`` el script imprime OMITIDO y sale."""

        modulo = importlib.import_module("scripts.verify_phishtank_live")
        monkeypatch.delenv("LINKGUARD_LIVE_TESTS", raising=False)
        # Sin rutas registradas: cualquier intento de red fallaría en respx.
        with respx.mock:
            codigo = asyncio.run(modulo.main())

        salida = capsys.readouterr().out
        assert codigo == 0
        assert json.loads(salida)["estado"] == "OMITIDO"
