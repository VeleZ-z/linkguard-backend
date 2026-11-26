"""Verificación opt-in de la hipótesis C6 con URLs reales de PhishTank.

Este script **no forma parte del servicio** y solo hace tráfico saliente cuando
``LINKGUARD_LIVE_TESTS=1``. Descarga una muestra del feed público de URLs
validadas, consulta cada variante normativa (RF-801) contra el endpoint de
PhishTank y reporta la tasa de acierto por variante, los primeros aciertos y
cualquier señal de límite de tasa.

Uso::

    LINKGUARD_LIVE_TESTS=1 .venv/bin/python scripts/verify_phishtank_live.py

La salida es JSON en ``stdout``; rediríjala a ``docs/reports/`` si desea
conservarla. Nunca imprime la ``PHISHTANK_APP_KEY`` ni las URLs consultadas.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import httpx

#: El directorio raíz del repo se añade para poder ejecutar el script directo.
ROOT: Path = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.clients.phishtank import VARIANT_LABELS, PhishtankClient  # noqa: E402

#: Feed público de URLs confirmadas como phishing, usado solo en este laboratorio.
FEED_URL: str = "https://data.phishtank.com/data/online-valid.json"

#: Número de URLs reales muestreadas (acota tiempo y carga sobre el tercero).
SAMPLE_SIZE: int = 20

#: Timeout por consulta individual; el presupuesto global se controla aquí.
QUERY_TIMEOUT: float = 4.0


def _activo() -> bool:
    """Indica si el operador autorizó explícitamente el tráfico real."""
    return os.getenv("LINKGUARD_LIVE_TESTS") == "1"


async def _descargar_muestra(http: httpx.AsyncClient) -> list[str]:
    """Obtiene hasta ``SAMPLE_SIZE`` URLs válidas del feed público."""
    respuesta = await http.get(FEED_URL)
    respuesta.raise_for_status()
    datos: Any = respuesta.json()
    if not isinstance(datos, list):
        raise ValueError("El feed público de PhishTank no devolvió una lista")

    urls: list[str] = []
    for entrada in datos:
        if not isinstance(entrada, dict):
            continue
        url = entrada.get("url")
        if isinstance(url, str) and url.startswith(("http://", "https://")):
            urls.append(url)
            if len(urls) >= SAMPLE_SIZE:
                break
    return urls


def _resumen(
    intentos: Counter[str],
    aciertos: Counter[str],
    primeros: Counter[str],
    rate_limits: int,
    errores: Counter[str],
) -> dict[str, Any]:
    """Compila el informe con tasas por variante y dictamen de C6."""
    por_variante: dict[str, dict[str, float | int]] = {}
    for etiqueta in VARIANT_LABELS:
        total = intentos[etiqueta]
        encontrados = aciertos[etiqueta]
        por_variante[etiqueta] = {
            "consultas": total,
            "aciertos": encontrados,
            "tasa": round(encontrados / total, 4) if total else 0.0,
            "primeros_aciertos": primeros[etiqueta],
        }

    original = por_variante["original_saneada"]["tasa"]
    normalizada = por_variante["normalizada"]["tasa"]
    if normalizada >= original and original < 1.0:
        c6 = "CONFIRMADA: normalizar puede perder coincidencias exactas; las variantes mitigan el riesgo"
    else:
        c6 = "DESCARTADA con la muestra analizada: normalizar no redujo los aciertos"

    return {
        "hipotesis_c6": c6,
        "muestras": sum(intentos.values()) // len(VARIANT_LABELS) if intentos else 0,
        "por_variante": por_variante,
        "rate_limits_429": rate_limits,
        "errores_por_tipo": dict(errores),
    }


async def main() -> int:
    """Ejecuta el experimento o lo omite si no hay autorización explícita."""
    if not _activo():
        print(
            json.dumps(
                {
                    "estado": "OMITIDO",
                    "motivo": "LINKGUARD_LIVE_TESTS != 1 (el CI nunca hace tráfico real)",
                },
                ensure_ascii=False,
            )
        )
        return 0

    cliente = PhishtankClient()
    intentos: Counter[str] = Counter()
    aciertos: Counter[str] = Counter()
    primeros: Counter[str] = Counter()
    errores: Counter[str] = Counter()
    rate_limits = 0

    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as http:
            urls = await _descargar_muestra(http)
    except httpx.HTTPStatusError as exc:
        # El feed público está limitado por IP (429). No es un fallo del motor:
        # se reporta como no verificable, sin traceback ni falsa confirmación.
        print(
            json.dumps(
                {
                    "estado": "BLOQUEADO",
                    "motivo": f"feed público devolvió HTTP {exc.response.status_code}",
                    "hipotesis_c6": "NO VERIFICADA: el feed de PhishTank está limitado por IP",
                },
                ensure_ascii=False,
            )
        )
        return 0
    except httpx.HTTPError as exc:
        print(
            json.dumps(
                {
                    "estado": "BLOQUEADO",
                    "motivo": f"error de red leyendo el feed: {type(exc).__name__}",
                    "hipotesis_c6": "NO VERIFICADA: no fue posible descargar la muestra",
                },
                ensure_ascii=False,
            )
        )
        return 0

    for url in urls:
        variantes = cliente.build_variants(url)
        ya_encontrado = False
        for indice, variante in enumerate(variantes):
            etiqueta = VARIANT_LABELS[indice] if indice < len(VARIANT_LABELS) else f"v{indice + 1}"
            intentos[etiqueta] += 1
            try:
                es_match, _ = await cliente.query_variant(variante, timeout=QUERY_TIMEOUT)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429:
                    rate_limits += 1
                errores[f"http_{exc.response.status_code}"] += 1
                continue
            except (httpx.HTTPError, ValueError) as exc:
                errores[type(exc).__name__] += 1
                continue

            if es_match:
                aciertos[etiqueta] += 1
                if not ya_encontrado:
                    primeros[etiqueta] += 1
                    ya_encontrado = True

    print(
        json.dumps(
            _resumen(intentos, aciertos, primeros, rate_limits, errores),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
