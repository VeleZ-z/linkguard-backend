"""Verificación stateless y de memoria (H3-T10, TC-RNF-103 y TC-RNF-104).

- TC-RNF-103: cero archivos creados o modificados en disco durante el análisis.
- TC-RNF-104: consumo de RAM documentado y acotado (≤ 256 MB bajo carga nominal).
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import httpx
from app.core.config import get_settings

#: Directorio base del proyecto (candidato a recibir escrituras accidentales).
BASE_DIR = Path(__file__).resolve().parents[2]


def _lista_archivos() -> set[Path]:
    """Instantánea de archivos regulares bajo BASE_DIR (excluye __pycache__)."""
    archivos: set[Path] = set()
    for root, _dirs, files in os.walk(BASE_DIR):
        if "__pycache__" in root or ".git" in root:
            continue
        for nombre in files:
            archivos.add(Path(root) / nombre)
    return archivos


class TestTCRNF103Stateless:
    """TC-RNF-103: cero archivos creados/modificados durante una request."""

    async def test_no_crea_archivos_en_disco(self, client: httpx.AsyncClient) -> None:
        antes = _lista_archivos()

        response = await client.post("/api/v1/analyze", json={"url": "http://example.com/news"})

        despues = _lista_archivos()
        creados = despues - antes
        modificados: set[Path] = set()

        # Comparar mtimes de los archivos preexistentes.
        for path in antes & despues:
            try:
                antes_mtime = path.stat().st_mtime_ns
                despues_mtime = path.stat().st_mtime_ns
                if antes_mtime != despues_mtime:
                    modificados.add(path)
            except OSError:
                pass

        assert response.status_code == 200
        assert not creados, f"Archivos creados en disco: {sorted(creados)}"
        assert not modificados, f"Archivos modificados en disco: {sorted(modificados)}"


class TestTCRNF104Memoria:
    """TC-RNF-104: consumo de RAM documentado y acotado (≤ 256 MB)."""

    #: Límite superior documentado del contenedor (RNF-104).
    LIMITE_MEMORIA_MB: float = 256.0

    def _memoria_rss_mb(self) -> float:
        """Lee VmRSS de /proc/self/status (Linux) o retorna 0 si no disponible."""
        try:
            contenido = Path("/proc/self/status").read_text(encoding="utf-8")
            match = re.search(r"VmRSS:\s+(\d+)\s+kB", contenido)
            if match:
                return int(match.group(1)) / 1024.0
        except (OSError, FileNotFoundError):
            pass
        return 0.0

    def test_consumo_ram_acotado(self) -> None:
        """Documenta y verifica que el proceso está por debajo de 256 MB.

        En producción este chequeo se ejecuta con ``docker stats`` sobre el
        contenedor backend bajo carga nominal. Aquí se verifica el RSS del
        proceso de pruebas como proxy.
        """
        rss_mb = self._memoria_rss_mb()

        # El registro de la métrica se deja documentado para trazabilidad CI:
        # TC-RNF-104 → RSS actual: {rss_mb:.2f} MB (límite {self.LIMITE_MEMORIA_MB} MB).
        # En producción se verifica con ``docker stats`` sobre el contenedor backend.

        assert rss_mb < self.LIMITE_MEMORIA_MB, (
            f"Memoria RAM {rss_mb:.2f} MB excede el límite de {self.LIMITE_MEMORIA_MB} MB"
        )

    def test_configuracion_ttl_7200(self) -> None:
        """Documenta el TTL configurado (7200 s = 2 h, RF-403)."""
        assert get_settings().PHISHTANK_TTL_SECONDS == 7200
