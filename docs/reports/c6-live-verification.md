# C6 — Verificación empírica de variantes de PhishTank (H5-T13)

**Fecha:** 2026-11-26 · **Modo:** opt-in, fuera de CI · **Interrumpidor:** `LINKGUARD_LIVE_TESTS=1`

## Resultado

**NO VERIFICADA.** El feed público `https://data.phishtank.com/data/online-valid.json` devolvió **HTTP 429 Too Many Requests** antes de obtener cualquier muestra. El script ya no termina con traceback: emite un JSON estructurado con `estado: "BLOQUEADO"` y `hipotesis_c6: "NO VERIFICADA..."`, y no consulta el endpoint de verificación.

```json
{"estado": "BLOQUEADO", "motivo": "feed público devolvió HTTP 429", "hipotesis_c6": "NO VERIFICADA: el feed de PhishTank está limitado por IP"}
```

Cabeceras observadas en el 429: `x-request-count: 7875`, `x-request-limit: 75`, `x-request-limit-interval: 259200` segundos. Es una cuota por IP compartida, ya agotada; no está relacionada con el motor ni con la configuración del repositorio. No hay `PHISHTANK_APP_KEY` configurada, por lo que la ruta con clave tampoco está disponible.

## Alcance

- `app/` no se modificó; el contrato `POST /api/v1/analyze` sigue congelado.
- `CI` sigue sin tráfico real: `tests/unit/test_ci_workflows.py` y `tests/unit/test_measure_rdap_gain.py` prohíben los interruptores.
- La mitigación de C6 (`build_variants`, presupuesto global de 4,0 s, caché por variante y `app_key` opcional) permanece implantada y cubierta por `tests/integration/test_phishtank_variants.py` con `respx`.

## Cómo reabrir

1. Configurar `PHISHTANK_APP_KEY` como variable de entorno/secret (nunca en el repo), **o** esperar a que se renueve la cuota de la IP.
2. Ejecutar fuera de CI: `LINKGUARD_LIVE_TESTS=1 .venv/bin/python scripts/verify_phishtank_live.py`.
3. conservar el JSON resultante aquí y actualizar §8 de `docs/reports/accuracy-v3.md`.

Hasta entonces C6 queda como **deuda externa declarada**, no como fallo de la certificación del Hito 5.
