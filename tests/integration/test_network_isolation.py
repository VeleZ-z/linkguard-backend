"""Prueba de aislamiento absoluto de red (H3-T09, TC-RNF-101, RNF-101).

Garantiza que el backend **nunca** abre un socket hacia el host de la URL que
el usuario solicita analizar. Usa ``respx`` con una única ruta mockada
(PHISHTANK_API_URL): cualquier intento de conectar a otro host falla con un
error de respx, haciendo rojo el test.
"""

from __future__ import annotations

import httpx
import pytest
import respx
from app.cache.phishtank_cache import reset_phishtank_cache
from app.clients.phishtank import PhishtankClient, get_phishtank_client, reset_phishtank_client
from app.core.config import get_settings
from app.schemas import PhishtankStatus

API_URL = get_settings().PHISHTANK_API_URL

#: Host que nunca debe ser contactado por el cliente de PhishTank.
HOST_ANALIZADO = "evil.example"
URL_ANALIZADA = f"http://{HOST_ANALIZADO}/login"


def _cliente_real(monkeypatch: pytest.MonkeyPatch) -> None:
    """Restaura el cliente real para que respx intercepte su httpx."""
    reset_phishtank_cache()
    reset_phishtank_client()
    monkeypatch.setattr("app.services.analyzer.get_phishtank_client", get_phishtank_client)


class TestAislamientoRed:
    """TC-RNF-101: cero peticiones al host de la URL analizada."""

    @respx.mock
    async def test_nunca_contacta_el_host_analizado(
        self, client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Solo se permite el endpoint de PhishTank. Cualquier otra conexión
        # (incluida evil.example) haría que respx lanzara AssertionError.
        respx.post(API_URL).mock(
            return_value=httpx.Response(
                200, json={"results": {"in_database": False, "valid": True}}
            )
        )
        _cliente_real(monkeypatch)

        response = await client.post("/api/v1/analyze", json={"url": URL_ANALIZADA})

        assert response.status_code == 200
        body = response.json()
        assert body["phishtank_status"] == PhishtankStatus.AVAILABLE

    @respx.mock
    async def test_respx_rechaza_cualquier_otro_host(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Si el cliente intentara contactar la URL analizada, respx falla."""
        # Sin mock para evil.example: respx debe rechazar la conexión.
        with pytest.raises(AssertionError):
            reset_phishtank_cache()
            cliente = PhishtankClient()
            monkeypatch.setattr("app.services.analyzer.get_phishtank_client", lambda: cliente)
            await cliente.check_url(URL_ANALIZADA)
