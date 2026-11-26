"""Guardias de CI para artefactos y tráfico opt-in (H5-T07, H5-OBS-05).

La remediación de la auditoría H5-T16 retiró el push directo del workflow de
refresco: toda regeneración debe llegar mediante PR revisable. Estas pruebas
impiden que esa decisión se revierta por accidente y comprueban que ningún
workflow habilita los interruptores de tráfico real.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
INTERRUPTORES = ("LINKGUARD_LIVE_TESTS", "LINKGUARD_RDAP_LIVE", "LINKGUARD_TIMEOUT_NETWORK_TESTS")


def _lineas_activas(ruta: Path) -> list[str]:
    """Devuelve las líneas del YAML que no son comentarios ni están vacías."""
    return [
        linea.strip()
        for linea in ruta.read_text(encoding="utf-8").splitlines()
        if linea.strip() and not linea.lstrip().startswith("#")
    ]


@pytest.fixture
def flujos() -> list[Path]:
    """Lista los workflows presentes; la ausencia de todos ellos es un error."""
    archivos = sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml"))
    assert archivos, "No hay workflows que inspeccionar"
    return archivos


def test_refresco_abre_pr_sin_push_directo() -> None:
    """El refresco semanal propone cambios, nunca los empuja a `main`."""
    ruta = WORKFLOWS / "refresh-reputation.yml"
    assert ruta.is_file()

    activas = _lineas_activas(ruta)
    assert any("create-pull-request" in linea for linea in activas)
    assert all(not linea.startswith("git push") for linea in activas)
    assert all("run: git push" not in linea for linea in activas)


def test_workflows_no_habilitan_trafico_real(flujos: list[Path]) -> None:
    """Ningún job activa los interruptores de pruebas con red."""
    for ruta in flujos:
        activas = _lineas_activas(ruta)
        for interruptor in INTERRUPTORES:
            assert not any(f"{interruptor}: 1" in linea for linea in activas)
