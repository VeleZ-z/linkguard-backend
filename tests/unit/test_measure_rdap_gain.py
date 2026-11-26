"""Pruebas del experimento RDAP (H5-T17) sin tráfico externo.

El arnés del laboratorio fija variables de entorno al importarse. Para que la
suite completa no herede ese estado, el módulo se importa dentro de una fixture
que restaura las variables y limpia la caché de ajustes al terminar cada prueba.
Además, el modo offline sustituye ``httpx.Client`` por un doble que falla si se
intenta construir: cualquier regresión que abra sockets en CI se detecta de
inmediato (RNF-101).
"""

from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest
from app.core.config import get_settings

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts" / "ml"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

CLAVES_ENTORNO = ("PHISHTANK_ENABLED", "ENABLE_V3_SCORING")


@pytest.fixture
def modulo() -> Any:
    """Importa el arnés y devuelve el entorno a su estado original."""
    originales = {clave: os.environ.get(clave) for clave in CLAVES_ENTORNO}
    try:
        importado = importlib.import_module("measure_rdap_gain")
    finally:
        for clave, valor in originales.items():
            if valor is None:
                os.environ.pop(clave, None)
            else:
                os.environ[clave] = valor
        get_settings.cache_clear()
    return importado


def test_dominio_sin_esquema(modulo: Any) -> None:
    """Las URLs del benchmark sin `://` no pierden el TLD."""
    assert modulo._dominio_de("example.com/login") == "example.com"
    assert modulo._dominio_de("https://sub.example.com/login") == "example.com"


def test_muestra_determinista_y_equilibrada(modulo: Any) -> None:
    """Una URL por dominio, con tope y semilla fija."""
    filas, dominios = modulo.seleccionar_muestra(10, 20)

    assert len(filas) == len(dominios)
    assert len(filas) <= 20
    assert sum(dominios.values()) == 10
    assert modulo.seleccionar_muestra(10, 20)[1] == dominios


def test_senal_solo_a_dominios_nuevos(modulo: Any) -> None:
    """+15 al dominio nuevo; respeta el tope de 30 en dominios confiables."""
    filas, _ = modulo.seleccionar_muestra(2, 2)
    evaluadas, _ = modulo.ev.evaluate_rows(filas)
    base = modulo.ev.score_stage(evaluadas, "feeds")
    dominio = modulo._dominio_de(filas[0].url)
    edades = {
        dominio: modulo.EdadDominio(dominio, 5, "ok", 0.0),
        "otro.com": modulo.EdadDominio("otro.com", None, "unavailable", 0.0),
    }

    enriquecidas = modulo.puntuar_con_senal(evaluadas, base, edades)

    assert enriquecidas[0] == min(100, base[0] + 15)
    assert enriquecidas[1] == base[1]


def test_modo_offline_no_construye_cliente(
    modulo: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """El modo por defecto solo lee caché: CI nunca abre conexiones."""

    def _prohibido(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("El modo offline no debe construir httpx.Client")

    monkeypatch.setattr(modulo.httpx, "Client", _prohibido)
    monkeypatch.setattr(modulo, "CACHE_PATH", tmp_path / "cache.json")
    monkeypatch.setattr(modulo, "BOOTSTRAP_PATH", tmp_path / "bootstrap.json")
    salida_json = tmp_path / "resultado.json"
    salida_md = tmp_path / "informe.md"

    codigo = modulo.main(
        [
            "--offline",
            "--max-domains",
            "6",
            "--per-class",
            "3",
            "--json-out",
            str(salida_json),
            "--report-out",
            str(salida_md),
        ]
    )

    assert codigo == 0
    datos = json.loads(salida_json.read_text(encoding="utf-8"))
    assert datos["modo"] == "offline"
    assert datos["medidas"]["dominios"] <= 6
    assert "## Decisión" in salida_md.read_text(encoding="utf-8")
    assert "no se implementa" in salida_md.read_text(encoding="utf-8")


def test_live_requiere_variable_de_entorno(
    modulo: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`--live` sin `LINKGUARD_RDAP_LIVE=1` degrada silenciosamente a offline."""
    monkeypatch.delenv(modulo.LIVE_ENV, raising=False)
    monkeypatch.setattr(modulo, "BOOTSTRAP_PATH", tmp_path / "nunca-existe.json")
    assert modulo.cargar_servidores(None) == modulo.FALLBACK_SERVERS
