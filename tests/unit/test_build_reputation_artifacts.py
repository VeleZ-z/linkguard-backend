"""Pruebas del filtrado abusable del generador de artefactos (H5-T05).

La auditoría H5-T16 marcó como riesgo latente la construcción de un regex con
``.*`` desde patrones con comodín. Estas pruebas fijan un emparejamiento lineal
y anclado por etiqueta, equivalente al del runtime, sin ``re.search``.
"""

from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts" / "ml"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


@pytest.fixture
def generador() -> Any:
    """Importa el generador sin ejecutar su punto de entrada."""
    return importlib.import_module("build_reputation_artifacts")


def test_coincidencia_exacta_y_por_etiqueta(generador: Any) -> None:
    """``web.app`` alcanza a sus subdominios, nunca a sufijosparciales."""
    assert generador._is_abusable("web.app", ["web.app"]) is True
    assert generador._is_abusable("x.web.app", ["web.app"]) is True
    assert generador._is_abusable("evilweb.app", ["web.app"]) is False
    assert generador._is_abusable("otro.example", ["web.app"]) is False


def test_comodin_no_usar_regex(generador: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """Un comodín solo admite subdominios y jamás invoca ``re.search``."""

    def _prohibido(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("El filtrado abusable no debe construir regex")

    monkeypatch.setattr(re, "search", _prohibido)

    assert generador._is_abusable("cuenta.ejemplo.com", ["*.ejemplo.com"]) is True
    assert generador._is_abusable("ejemplo.com", ["*.ejemplo.com"]) is True
    assert generador._is_abusable("mal-ejemplo.com", ["*.ejemplo.com"]) is False


def test_entrada_hostil_no_backtrackea(generador: Any) -> None:
    """Una etiqueta muy larga sin coincidencia se resuelve en tiempo lineal."""
    hostil = "a" * 50_000 + ".no-abusable.test"

    assert generador._is_abusable(hostil, ["*.abusable.test"]) is False
