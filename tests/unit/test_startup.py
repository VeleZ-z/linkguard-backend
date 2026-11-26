"""RNF-107/RNF-109: verificación de artefactos disparada al arranque.

El ciclo de vida inicia la carga en segundo plano: ``/health`` no espera a
que terminen los 9 MB de artefactos ni al modelo lineal.
"""

from __future__ import annotations

import asyncio

import pytest
from app.main import lifespan
from app.ml.model import clear_model_cache, get_model
from app.reputation import loader
from fastapi import FastAPI


def test_arranque_verifica_artefactos_y_modelo(monkeypatch: pytest.MonkeyPatch) -> None:
    """La tarea de arranque deja los tres artefactos y el modelo listos."""
    monkeypatch.setattr(loader, "_loaded", False)
    monkeypatch.setattr(
        loader,
        "_load_status",
        {"allowlist": "missing", "blocklist_urls": "missing", "blocklist_hosts": "missing"},
    )
    clear_model_cache()

    async def escenario() -> tuple[dict[str, str], bool]:
        application = FastAPI()
        async with lifespan(application):
            tarea = application.state.startup_task
            assert tarea is not None
            assert tarea.get_name() == "linkguard-artefactos"
            # El cuerpo del lifespan ya cedió el control: /health no esperó.
            await tarea
        return loader.get_load_status(), get_model().available

    estados, modelo_disponible = asyncio.run(escenario())

    assert estados == {
        "allowlist": "ok",
        "blocklist_urls": "ok",
        "blocklist_hosts": "ok",
    }
    assert modelo_disponible is True
