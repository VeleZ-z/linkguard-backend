"""Experimento H5-T17: ganancia real de la edad de dominio vía RDAP (RF-901).

Mide la señal sobre una muestra determinista y **retenida** del benchmark del
laboratorio (≤ 2 000 dominios únicos), evalúa el sistema v3 congelado y compara
``Recall@FPR`` antes y después de añadir ``NEW_DOMAIN`` (+15 si el dominio tiene
menos de 30 días). Solo se envía el **dominio registrable** a servidores RDAP
públicos; nunca la URL completa ni el host analizado (RNF-101).

El tráfico real es **opt-in**: hace falta ``LINKGUARD_RDAP_LIVE=1`` y ``--live``.
Sin esas dos condiciones el script trabaja solo con la caché en disco, de modo
que CI y las pruebas no generan tráfico externo. Las respuestas se guardan en
``data/processed/`` (ignorado por git) para poder regenerar el informe sin red.

Uso::

    .venv/bin/python scripts/ml/measure_rdap_gain.py --offline
    LINKGUARD_RDAP_LIVE=1 .venv/bin/python scripts/ml/measure_rdap_gain.py --live --max-domains 1600
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Final
from urllib.parse import urlsplit

ROOT: Path = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SCRIPTS_DIR: Path = ROOT / "scripts" / "ml"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

# El laboratorio jamás habla con el host analizado ni con PhishTank.
os.environ["PHISHTANK_ENABLED"] = "false"
os.environ["ENABLE_V3_SCORING"] = "true"

import evaluate_v3 as ev  # noqa: E402
import httpx  # noqa: E402
from app.normalization.psl import registrable_domain  # noqa: E402
from app.scoring.scorer import LOW_MAX  # noqa: E402

BENCHMARK_PATH: Final[Path] = ROOT / "data" / "processed" / "benchmark.tsv"
BOOTSTRAP_PATH: Final[Path] = ROOT / "data" / "processed" / "rdap_bootstrap.json"
CACHE_PATH: Final[Path] = ROOT / "data" / "processed" / "rdap_cache.json"
JSON_PATH: Final[Path] = ROOT / "data" / "processed" / "rdap_experiment.json"
REPORT_PATH: Final[Path] = ROOT / "docs" / "reports" / "rdap-experiment.md"

BOOTSTRAP_URL: Final[str] = "https://data.iana.org/rdap/dns.json"
LIVE_ENV: Final[str] = "LINKGUARD_RDAP_LIVE"
USER_AGENT: Final[str] = "linkguard-rdap-experiment/1.0"

EXAMPLE_DOMAIN: Final[str] = "vgydea.com"

NEW_DOMAIN_DAYS: Final[int] = 30
NEW_DOMAIN_POINTS: Final[int] = 15
FPR_TARGETS: Final[tuple[float, ...]] = (0.01, 0.03)
MAX_DOMAINS: Final[int] = 2000
SEED: Final[int] = 5

#: Servidores de respaldo si no hay bootstrap descargado (modo sin red).
FALLBACK_SERVERS: Final[dict[str, str]] = {
    "com": "https://rdap.verisign.com/com/v1",
    "net": "https://rdap.verisign.com/net/v1",
    "org": "https://rdap.publicinterestregistry.org/rdap",
    "io": "https://rdap.nic.io",
    "dev": "https://www.registry.google/rdap",
}


def _dominio_de(url: str) -> str:
    """Extrae el dominio registrable incluso si la URL no trae esquema."""
    candidato = url if "://" in url else "http://" + url
    try:
        host = (urlsplit(candidato).hostname or "").lower().rstrip(".")
    except ValueError:
        return ""
    return registrable_domain(host)


@dataclass(frozen=True, slots=True)
class EdadDominio:
    """Resultado de una consulta RDAP para un dominio registrable."""

    dominio: str
    dias: int | None
    estado: str
    latencia_ms: float


def _leer_json(ruta: Path) -> Any:
    """Lee un JSON auxiliar; devuelve None si no existe o es inválido."""
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _escribir_json(ruta: Path, contenido: Any) -> None:
    """Escribe un JSON con orden estable y salida final newline."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(
        json.dumps(contenido, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def cargar_servidores(cliente: httpx.Client | None) -> dict[str, str]:
    """Obtiene el mapa TLD → servidor RDAP desde IANA (o la caché)."""
    guardado = _leer_json(BOOTSTRAP_PATH)
    if isinstance(guardado, dict) and guardado:
        return {str(clave): str(valor) for clave, valor in guardado.items()}

    if cliente is None:
        return dict(FALLBACK_SERVERS)

    respuesta = cliente.get(BOOTSTRAP_URL, timeout=10.0)
    respuesta.raise_for_status()
    datos: Any = respuesta.json()
    servidores: dict[str, str] = {}
    for servicio in datos.get("services", []):
        tlds, urls = servicio[0], servicio[1]
        if not tlds or not urls:
            continue
        base = str(urls[0]).rstrip("/")
        for tld in tlds:
            servidores.setdefault(str(tld).lower(), base)
    _escribir_json(BOOTSTRAP_PATH, servidores)
    return servidores


def consultar_edad(
    cliente: httpx.Client | None,
    dominio: str,
    servidores: dict[str, str],
    cache: dict[str, Any],
    delay: float,
    timeout: float,
) -> EdadDominio:
    """Consulta la fecha de registro del dominio, con pausa y caché."""
    guardado = cache.get(dominio)
    if isinstance(guardado, dict):
        return EdadDominio(
            dominio=dominio,
            dias=guardado.get("dias"),
            estado=str(guardado.get("estado", "cached")),
            latencia_ms=float(guardado.get("latencia_ms", 0.0) or 0.0),
        )

    tld = dominio.rsplit(".", 1)[-1].lower()
    base = servidores.get(tld)
    if cliente is None:
        # Sin cliente no hubo consulta: no debe confundirse con un TLD sin servidor.
        return EdadDominio(dominio, None, "no_consultado", 0.0)
    if not base:
        estado_sin_servidor = EdadDominio(dominio, None, "sin_servidor", 0.0)
        cache[dominio] = {"dias": None, "estado": "sin_servidor", "latencia_ms": 0.0}
        return estado_sin_servidor

    url = f"{base}/domain/{dominio}"
    estado = "unavailable"
    dias: int | None = None
    latencia = 0.0
    for _intento in range(3):
        time.sleep(delay + random.random() * 0.05)
        iniciado = perf_counter()
        try:
            respuesta = cliente.get(
                url,
                headers={"Accept": "application/rdap+json", "User-Agent": USER_AGENT},
                timeout=timeout,
            )
        except httpx.HTTPError as exc:
            estado = f"error_{type(exc).__name__}"
            continue
        finally:
            latencia = max(latencia, (perf_counter() - iniciado) * 1000.0)

        if respuesta.status_code == 429:
            estado = "rate_limited"
            cabecera = respuesta.headers.get("retry-after", "")
            try:
                time.sleep(min(float(cabecera), 5.0))
            except ValueError:
                time.sleep(1.0)
            continue
        if respuesta.status_code == 404:
            estado = "not_registered"
            break
        if respuesta.status_code != 200:
            estado = f"http_{respuesta.status_code}"
            continue

        try:
            datos: Any = respuesta.json()
            fecha = next(
                (
                    evento.get("eventDate")
                    for evento in datos.get("events", [])
                    if evento.get("eventAction") == "registration"
                ),
                None,
            )
            registrado = datetime.fromisoformat(str(fecha).replace("Z", "+00:00"))
            if registrado.tzinfo is None:
                registrado = registrado.replace(tzinfo=UTC)
            dias = max(0, (datetime.now(UTC) - registrado).days)
            estado = "ok"
        except (ValueError, TypeError, AttributeError, KeyError):
            estado = "sin_fecha"
        break

    cache[dominio] = {
        "dias": dias,
        "estado": estado,
        "latencia_ms": round(latencia, 3),
    }
    return EdadDominio(dominio, dias, estado, latencia)


def seleccionar_muestra(por_clase: int, total: int) -> tuple[list[ev.Row], dict[str, int]]:
    """Selecciona una URL por dominio, equilibrando positivos y negativos."""
    por_etiqueta: dict[int, dict[str, ev.Row]] = {0: {}, 1: {}}
    with BENCHMARK_PATH.open("r", encoding="utf-8") as handle:
        for campos in csv.DictReader(handle, delimiter="\t"):
            url = campos.get("url", "").strip()
            if not url:
                continue
            etiqueta = int(campos["label"])
            dominio = _dominio_de(url)
            if not dominio:
                continue
            por_etiqueta[etiqueta].setdefault(
                dominio,
                ev.Row(url, etiqueta, campos.get("source", ""), campos.get("year", "")),
            )

    azar = random.Random(SEED)
    elegidas: list[ev.Row] = []
    for etiqueta in (1, 0):
        dominios = sorted(por_etiqueta[etiqueta])
        azar.shuffle(dominios)
        elegidas.extend(por_etiqueta[etiqueta][dominio] for dominio in dominios[:por_clase])

    if len(elegidas) > total:
        elegidas = elegidas[:total]
    dominios_elegidos = {_dominio_de(fila.url): fila.label for fila in elegidas}
    return elegidas, dominios_elegidos


def puntuar_con_senal(
    evaluadas: list[ev.Evaluated],
    baseline: list[int],
    edades: dict[str, EdadDominio],
) -> list[int]:
    """Añade +15 por dominio nuevo, respetando el tope de dominio confiable."""
    resultado: list[int] = []
    for elemento, score in zip(evaluadas, baseline, strict=True):
        dominio = _dominio_de(elemento.row.url)
        informacion = edades.get(dominio)
        if informacion and informacion.dias is not None and informacion.dias < NEW_DOMAIN_DAYS:
            nuevo = min(100, score + NEW_DOMAIN_POINTS)
            if elemento.allowlisted and not elemento.abusable:
                nuevo = min(nuevo, LOW_MAX)
            resultado.append(nuevo)
        else:
            resultado.append(score)
    return resultado


def generar_informe(datos: dict[str, Any], ruta: Path) -> None:
    """Escribe el informe reproducible del experimento."""
    m = datos["medidas"]
    lineas = [
        "# Experimento RDAP — edad de dominio (H5-T17 / RF-901)",
        "",
        f"Generado: `{datos['generado']}` · modo: `{datos['modo']}` · semilla: {SEED}.",
        "",
        "## Protocolo",
        "",
        "- Muestra retenida del benchmark congelado (`data/processed/benchmark.tsv`), "
        "una URL por dominio registrable, equilibrada entre positivos y negativos.",
        "- El sistema v3 se evalúa en proceso con PhishTank deshabilitado y sin "
        "tráfico hacia el host analizado (RNF-101). Umbrales y allowlist intactos.",
        "- Solo se consulta el dominio registrable a servidores RDAP públicos "
        "obtenidos del bootstrap de IANA. Pausa configurable entre consultas, "
        "3 reintentos ante fallo y caché en disco.",
        "- La señal `NEW_DOMAIN` suma +15 si la fecha de registro tiene menos de "
        "30 días; los dominios allowlisted no abusables siguen topados en 30.",
        "- `Recall@FPR` barre umbrales y toma el máximo recall con FPR ≤ objetivo, "
        "igual que el protocolo del adendo §7. Objetivo primario: FPR ≤ 3 %.",
        "",
        "## Muestra y cobertura",
        "",
        "| Métrica | Valor |",
        "| :-- | --: |",
        f"| Dominios únicos consultados | {m['dominios']} |",
        f"| Positivos / negativos | {m['positivos']} / {m['negativos']} |",
        f"| Respuestas con fecha de registro | {m['con_fecha']} |",
        f"| Dominios nuevos (< 30 días) | {m['nuevos']} |",
        f"| Nuevos positivos / negativos | {m['nuevos_positivos']} / {m['nuevos_negativos']} |",
        f"| Sin servidor / no registrados / errores / no consultados (offline) | "
        f"{m['sin_servidor']} / {m['no_registrados']} / {m['errores']} / "
        f"{m['no_consultados']} |",
        "",
        "## Resultado",
        "",
        "| FPR objetivo | Recall v3 | Recall + RDAP | Δ (pp) | Umbral v3 → +RDAP |",
        "| --: | --: | --: | --: | --: |",
    ]
    for objetivo in FPR_TARGETS:
        clave = f"{objetivo:.3f}"
        base = m["recall_base"][clave]
        nuevo = m["recall_rdap"][clave]
        delta = (nuevo["recall"] - base["recall"]) * 100.0
        lineas.append(
            f"| ≤ {objetivo:.0%} | {base['recall']:.3f} | {nuevo['recall']:.3f} | "
            f"{delta:+.2f} | {base['umbral']:.0f} → {nuevo['umbral']:.0f} |"
        )
    tasa_nuevos = m["nuevos_positivos"] / max(1, m["positivos"])
    if not datos["decision"]["aprobar"] and tasa_nuevos < 0.05:
        lineas += [
            "",
            "## Interpretación",
            "",
            f"Solo {m['nuevos_positivos']} de {m['positivos']} positivos "
            f"({tasa_nuevos:.1%}) tenían menos de 30 días al consultarlos. El corpus "
            "congelado está formado por campañas ya reportadas, por lo que la edad "
            "no discrimina entre clase positiva y negativa: la señal no puede elevar "
            "el recall sin elevar también los falsos positivos. **No se bajaron "
            "umbrales ni se relajó la allowlist para forzar la mejora.** Una futura "
            "evaluación con feeds de phishing fresco y dominios aleatorios cortos de "
            "registro reciente debe repetir este protocolo antes de reabrir H5-T17; "
            "la forma del nombre, por sí sola, no basta (ver caso ilustrativo).",
        ]
    caso = datos.get("caso_ilustrativo") or {}
    if caso:
        dias = caso.get("dias")
        detalle = (
            f"registrado hace **{dias} días**"
            if dias is not None
            else f"sin fecha de registro (`{caso.get('estado')}`)"
        )
        dispara = "sí" if dias is not None and dias < NEW_DOMAIN_DAYS else "no"
        lineas += [
            "",
            "## Caso ilustrativo",
            "",
            f"`{caso['dominio']}`: {detalle}. `NEW_DOMAIN` {dispara} dispara: la "
            "heurística de dominio aleatorio corto no se beneficia de RDAP en este "
            "ejemplo cuando el registro es antiguo.",
        ]
    lineas += [
        "",
        "## Latencia",
        "",
        "| Métrica | ms |",
        "| :-- | --: |",
        f"| p95 análisis v3 local | {m['p95_local_ms']:.2f} |",
        f"| p95 consulta RDAP | {m['p95_rdap_ms']:.2f} |",
        f"| p95 total (v3 + RDAP) | {m['p95_total_ms']:.2f} |",
        "",
        "## Decisión",
        "",
        datos["decision"]["texto"],
        "",
        "- Criterio: mejora ≥ 3 puntos de recall a FPR ≤ 3 % y p95 total ≤ 1 500 ms.",
        "- Si no se cumple, **no se implementa** el cliente RDAP en `app/`; el "
        "experimento queda como evidencia y `ENABLE_RDAP` no se añade.",
        "",
        "## Limitaciones y privacidad",
        "",
        "- Los positivos del benchmark ya fueron reportados y muchos dominios "
        "fueron dados de baja: la fecha de registro no siempre describe phishing fresco.",
        "- Un 404 se trata como «no registrado»/indisponible, nunca como dominio nuevo.",
        "- Solo sale el dominio registrable hacia el servidor RDAP de su TLD; nunca "
        "la URL, el path ni datos del usuario. El tráfico real requiere "
        f"`{LIVE_ENV}=1` y `--live`: **CI no realiza consultas**.",
        "- El modo `--offline` reproduce el informe desde la caché; las fechas se "
        "miden relativas al día de la consulta, por lo que el resultado es estable "
        "mientras la caché no se refresque. Las entradas servidas desde caché "
        "registran 0 ms: una regeneración offline da una cota inferior de la "
        "latencia. En la pasada `live` se mide solo la latencia HTTP; no se "
        "incluyen las pausas entre consultas ni el costo de programar al productor.",
    ]
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text("\n".join(lineas) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """Ejecuta el experimento y escribe JSON e informe."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="permite consultas RDAP reales")
    parser.add_argument("--offline", action="store_true", help="solo usa la caché en disco")
    parser.add_argument("--max-domains", type=int, default=MAX_DOMAINS)
    parser.add_argument("--per-class", type=int, default=MAX_DOMAINS // 2)
    parser.add_argument("--delay", type=float, default=0.20, help="pausa entre consultas")
    parser.add_argument("--timeout", type=float, default=3.0)
    parser.add_argument("--json-out", type=Path, default=JSON_PATH)
    parser.add_argument("--report-out", type=Path, default=REPORT_PATH)
    args = parser.parse_args(argv)

    if args.live and args.offline:
        parser.error("--live y --offline son excluyentes")
    if os.getenv(LIVE_ENV) != "1":
        args.live = False
    if args.live and args.max_domains > MAX_DOMAINS:
        parser.error(f"--max-domains no puede superar {MAX_DOMAINS}")

    filas, dominios = seleccionar_muestra(args.per_class, args.max_domains)
    evaluadas, errores = ev.evaluate_rows(filas)
    baseline = ev.score_stage(evaluadas, "feeds")

    cache: dict[str, Any] = {}
    guardado = _leer_json(CACHE_PATH)
    if isinstance(guardado, dict) and isinstance(guardado.get("entries"), dict):
        cache = guardado["entries"]

    modo = "live" if args.live else "offline"
    cliente = httpx.Client(timeout=args.timeout, follow_redirects=False) if args.live else None
    edades: dict[str, EdadDominio] = {}
    servidores = dict(FALLBACK_SERVERS)
    try:
        servidores = cargar_servidores(cliente)
        for indice, dominio in enumerate(sorted(dominios), start=1):
            edades[dominio] = consultar_edad(
                cliente, dominio, servidores, cache, args.delay, args.timeout
            )
            if args.live and indice % 50 == 0:
                # Persistencia incremental: una interrupción no pierde 1 600 consultas.
                _escribir_json(
                    CACHE_PATH,
                    {"updated_at": datetime.now(UTC).isoformat(), "entries": cache},
                )
                print(f"  RDAP {indice}/{len(dominios)}", flush=True)
    finally:
        # Consulta ilustrativa: el dominio del riesgo §10, nunca la URL completa.
        caso = consultar_edad(cliente, EXAMPLE_DOMAIN, servidores, cache, args.delay, args.timeout)
        if cliente is not None:
            cliente.close()
        _escribir_json(
            CACHE_PATH,
            {"updated_at": datetime.now(UTC).isoformat(), "entries": cache},
        )

    enriquecidas = puntuar_con_senal(evaluadas, baseline, edades)
    recall_base = ev.recall_at_fpr(evaluadas, baseline, FPR_TARGETS)
    recall_rdap = ev.recall_at_fpr(evaluadas, enriquecidas, FPR_TARGETS)

    latencias_rdap = [info.latencia_ms for info in edades.values()]
    totales = [
        elemento.v3_ms + edades[_dominio_de(elemento.row.url)].latencia_ms
        for elemento in evaluadas
        if _dominio_de(elemento.row.url) in edades
    ]
    p95_total = ev.percentile(totales, 0.95)
    ganancia = (recall_rdap["0.030"]["recall"] - recall_base["0.030"]["recall"]) * 100.0
    cumple = ganancia >= 3.0 and p95_total <= 1500.0
    decision = {
        "ganancia_pp_fpr_3": round(ganancia, 3),
        "p95_total_ms": round(p95_total, 3),
        "criterio_recall": ganancia >= 3.0,
        "criterio_latencia": p95_total <= 1500.0,
        "aprobar": cumple,
        "texto": (
            "**CUMPLE el criterio de promoción**: se autoriza implementar el cliente "
            "RDAP con `ENABLE_RDAP=false` por defecto y evidencia `NEW_DOMAIN`."
            if cumple
            else "**NO cumple el criterio de promoción**: no se implementa el cliente "
            "RDAP en producción; la señal queda documentada como experimento negativo."
        ),
    }

    datos: dict[str, Any] = {
        "generado": datetime.now(UTC).isoformat(),
        "modo": modo,
        "semilla": SEED,
        "criterio": {
            "ganancia_min_pp": 3.0,
            "fpr_objetivo": 0.03,
            "p95_max_ms": 1500.0,
            "dominios_max": MAX_DOMAINS,
        },
        "medidas": {
            "dominios": len(dominios),
            "positivos": sum(dominios.values()),
            "negativos": len(dominios) - sum(dominios.values()),
            "errores_evaluacion": errores,
            "con_fecha": sum(info.dias is not None for info in edades.values()),
            "nuevos": sum(
                info.dias is not None and info.dias < NEW_DOMAIN_DAYS for info in edades.values()
            ),
            "nuevos_positivos": sum(
                info.dias is not None and info.dias < NEW_DOMAIN_DAYS and dominios.get(dominio) == 1
                for dominio, info in edades.items()
            ),
            "nuevos_negativos": sum(
                info.dias is not None and info.dias < NEW_DOMAIN_DAYS and dominios.get(dominio) == 0
                for dominio, info in edades.items()
            ),
            "sin_servidor": sum(info.estado == "sin_servidor" for info in edades.values()),
            "no_registrados": sum(info.estado == "not_registered" for info in edades.values()),
            "errores": sum(
                info.estado not in {"ok", "sin_servidor", "not_registered", "no_consultado"}
                for info in edades.values()
            ),
            "no_consultados": sum(info.estado == "no_consultado" for info in edades.values()),
            "recall_base": recall_base,
            "recall_rdap": recall_rdap,
            "p95_local_ms": round(ev.percentile([e.v3_ms for e in evaluadas], 0.95), 3),
            "p95_rdap_ms": round(ev.percentile(latencias_rdap, 0.95), 3),
            "p95_total_ms": round(p95_total, 3),
        },
        "caso_ilustrativo": {
            "dominio": caso.dominio,
            "dias": caso.dias,
            "estado": caso.estado,
        },
        "decision": decision,
    }
    _escribir_json(args.json_out, datos)
    generar_informe(datos, args.report_out)

    print(
        f"dominios={len(dominios)} nuevos={datos['medidas']['nuevos']} "
        f"ganancia_pp={ganancia:+.2f} p95_total={p95_total:.1f}ms "
        f"aprobar={cumple}"
    )
    print(f"informe: {args.report_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
