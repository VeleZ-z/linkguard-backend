# Hito 3 — Cliente Asíncrono PhishTank + Resiliencia
## Timeout 4.0s · Caché LRU (TTL 2h) · Fallback elegante

> Repo: `linkguard-backend` · Depende de: Hito 2 (scorer/evidencias) · Bloquea a: Hito 4
> Requisitos núcleo: `RF-401`…`RF-405`, `RNF-101`, `RNF-103`, `RNF-104`

**Objetivo:** integrar la consulta de reputación externa de forma **no bloqueante y resiliente**, con caché volátil en RAM y degradación elegante, garantizando que un fallo de red nunca produzca un error 500 al cliente. Al cerrar el hito, `MATCH_PHISHTANK` suma `+50` y fuerza **Riesgo Alto**, y los estados `available`/`timeout`/`unavailable`/`cached` quedan demostrados.

---

## 3.1 Caché volátil

- [x] **H3-T01 · Caché LRU con TTL** `[RF-403]` `[RNF-103]`
  - 📄 Crear: `linkguard-backend/app/cache/ttl_lru.py`
  - 🤖 `build`
  - ✅ Estructura LRU en memoria (RAM, sin persistencia) con TTL configurable (`PHISHTANK_TTL_SECONDS=7200`); API `get(key)`, `set(key, value)`, expiración por tiempo; seguro para `asyncio` (un solo event loop). Sin escritura a disco (RNF-103).

## 3.2 Cliente HTTP

- [x] **H3-T02 · Cliente asíncrono de PhishTank** `[RF-401]` `[RF-402]`
  - 📄 Crear: `linkguard-backend/app/clients/phishtank.py`
  - 🤖 `build`
  - ✅ `httpx.AsyncClient` con `timeout=PHISHTANK_TIMEOUT` (4.0 s) parametrizable; `check_url(url)` consulta la API pública y normaliza la respuesta a un tipo interno (`is_match: bool`, `status: str`). `User-Agent` propio; sin claves en duro.

- [x] **H3-T03 · Manejo de timeout y errores (fallback)** `[RF-404]`
  - 📄 Modificar: `linkguard-backend/app/clients/phishtank.py`
  - 🤖 `build`
  - ✅ Captura silenciosa de `httpx.TimeoutException` → `status="timeout"`; errores de red / `4xx` / `5xx` → `status="unavailable"`. **Nunca** propaga excepción al handler (cero 500); retorna resultado neutro (`is_match=False`).

- [x] **H3-T04 · Elevación de riesgo por reputación** `[RF-405]`
  - 📄 Modificar: `linkguard-backend/app/scoring/scorer.py`, `linkguard-backend/app/scoring/evidence.py`
  - 🤖 `build`
  - ✅ Si `is_match=True`: `+50` con evidencia `MATCH_PHISHTANK` ("Reporte en lista negra de PhishTank") y **forzar** `risk_level="Alto"` aunque el score léxico sea bajo. Caso `TC-RF-401`; no match no suma (`TC-RF-402`).

## 3.3 Orquestación concurrente

- [x] **H3-T05 · Orquestador de análisis concurrente** `[RF-401]`
  - 📄 Crear: `linkguard-backend/app/services/analyzer.py`
  - 🤖 `build`
  - ✅ `analyze_url(url)` ejecuta en paralelo `asyncio.gather(run_rules(...), phishtank.check_url(...))`; mide `execution_time_ms`; combina score léxico + reputación; propaga `phishtank_status` a la respuesta.

- [x] **H3-T06 · Conectar orquestador al endpoint** `[RF-401]`
  - 📄 Modificar: `linkguard-backend/app/api/v1/analyze.py`
  - 🤖 `build`
  - ✅ El endpoint usa `services.analyzer.analyze_url`; respuesta mantiene el contrato §6 e incorpora `phishtank_status` real. Siempre `HTTP 200` ante fallos de reputación (`TC-RF-403`, `TC-RF-404`).

## 3.4 Pruebas de resiliencia y aislamiento

- [x] **H3-T07 · Tests unitarios de la caché** `[RF-403]`
  - 📄 Crear: `linkguard-backend/tests/unit/test_cache.py`
  - 🤖 `tester`
  - ✅ hit/miss; expiración por TTL; `TC-RF-405` (misma URL 2 veces en < 2 h → recuperación inmediata `< 1 ms`, `status="cached"`).

- [x] **H3-T08 · Tests de integración con `respx` (mocks estrictos)** `[RF-401]`…`[RF-405]`
  - 📄 Crear: `linkguard-backend/tests/integration/test_phishtank_resilience.py`
  - 🤖 `tester`
  - ✅ `TC-RF-401` (200 ms, encontrada → +50 y Alto), `TC-RF-402` (no encontrada → solo léxico), `TC-RF-403` (delay > 4 s → `timeout` + HTTP 200), `TC-RF-404` (HTTP 503 → `unavailable` + HTTP 200). **Prohibido** tráfico real saliente.

- [x] **H3-T09 · Test de aislamiento absoluto de red** `[RNF-101]`
  - 📄 Crear: `linkguard-backend/tests/integration/test_network_isolation.py`
  - 🤖 `tester`
  - ✅ Guard de sockets / `respx` que falla si se intenta conectar al host de la URL analizada (`TC-RNF-101`): cero peticiones a `scheme://netloc` del input.

- [x] **H3-T10 · Verificación stateless y de memoria** `[RNF-103]` `[RNF-104]`
  - 📄 Crear: `linkguard-backend/tests/integration/test_stateless.py`
  - 🤖 `tester`
  - ✅ `TC-RNF-103`: cero archivos creados/modificados durante una request; `TC-RNF-104`: chequeo documentado de RAM del contenedor `≤ 256 MB` (`docker stats`, script o procedimiento).

- [x] **H3-T11 · Auditoría de seguridad del Hito 3**
  - 🤖 `security-auditor`
  - ✅ REVISAR: ausencia de SSRF (nunca pedir la URL del usuario), timeout efectivo, sin credenciales/API keys en duro, manejo de errores sin fuga de trazas, `pip-audit` sin high/critical (o con riesgo aceptado y documentado).

### Criterios de salida del Hito 3
- [x] `TC-RF-401`…`405` en verde con mocks (sin red real).
- [x] Cualquier fallo de PhishTank devuelve `HTTP 200` con `phishtank_status` `timeout`/`unavailable`.
- [x] `MATCH_PHISHTANK` (+50) fuerza Riesgo Alto.
- [x] `TC-RNF-101` (aislamiento) y `TC-RNF-103` (stateless) verificados.

---

## 3.5 Dictamen de la auditoría (H3-T11)

**DICTAMEN: APROBADO.** El Hito 3 queda cerrado y certificado.

| Pilar | Veredicto | Evidencia principal |
| :--- | :--- | :--- |
| SSRF / RNF-101 | APROBADO | Único `client.post` en `app/clients/phishtank.py:86-89`; destino fijo `PHISHTANK_API_URL`, el input viaja solo como cuerpo; `follow_redirects=False`. |
| Timeout 4.0 s / RF-402 | APROBADO | `app/clients/phishtank.py:81`; probado con transporte real: aborta a los 4.01 s → `timeout`. |
| Degradación elegante / RF-404 | APROBADO | `app/clients/phishtank.py:112-115` + guarda extra `app/services/analyzer.py:47-54`; HTTP 200 con `timeout`/`unavailable`, nunca 500. |
| Secretos | APROBADO | Cero API keys o tokens en duro; todo por `BaseSettings`; `.env` fuera de Git. |
| Stateless / RAM / RNF-103,104 | APROBADO | Cero escrituras en disco; RSS medido 41.98 MB con la caché al tope (4096 entradas). |
| SAST y dependencias | APROBADO | `bandit -r ./app -ll` → 0 issues; `pip-audit` (prod y dev) → sin vulnerabilidades conocidas. |

### Observaciones y resolución

| ID | Severidad | Ubicación | Estado |
| :--- | :--- | :--- | :--- |
| OBS-1 | LOW | `app/core/config.py` | **Resuelto**: `PHISHTANK_API_URL` exige host exacto en la allowlist `PHISHTANK_ALLOWED_HOSTS` (`checkurl.phishtank.com`), además de HTTP(S) absoluto y sin credenciales embebidas. Rechaza IPs, mirrors no autorizados y sufijos tipo `checkurl.phishtank.com.evil.example`. |
| OBS-2 | LOW | `app/core/config.py` | `CORS_ORIGINS` admitía `"*"`. **Resuelto**: validador que rechaza cualquier comodín. |
| OBS-3 | LOW | `Dockerfile` (CMD de uvicorn) | **Resuelto**: el `CMD` arranca con `--proxy-headers --forwarded-allow-ips='*'` y `${PORT:-8000}`; Uvicorn reescribe `scope["client"]` con `X-Forwarded-For`, por lo que `get_remote_address` ve la IP real del cliente. Cubierto por `TestIpRealDetrasDeProxy` en `tests/integration/test_rate_limit.py` y verificado en el contenedor real: 31 peticiones con la misma IP → la 31 recibe 429; otra IP → 200. El `HEALTHCHECK` usa el mismo `PORT` para no fallar en Render. |
| OBS-4 | LOW (solo CI/dev) | `requirements-dev.txt`, `pyproject.toml` | `pytest` 8.4.2 arrastraba `PYSEC-2026-1845` y el pin `<9.0.0` bloqueaba la versión corregida. **Resuelto**: pins actualizados a `pytest>=9.0.3`, `pytest-cov>=7`, `pytest-asyncio>=1`; `pip-audit` de dev queda limpio. |
| OBS-5 | LOW | `app/main.py:99` | `logger.exception` escribe el traceback completo en stdout; si la excepción incluye el input, la URL analizada queda en el log del **servidor** (la respuesta HTTP al cliente sigue limpia). **Pendiente**: registrar solo el tipo de excepción o sanear con `hash_sensitive`. |
| OBS-6 | INFO | `tests/integration/test_phishtank_timeout_real.py` | Excepción aceptada a la regla de mocks: es la única prueba que abre un socket, contra un doble local en `127.0.0.1` (sin tráfico externo) y es **opt-in** (`LINKGUARD_TIMEOUT_NETWORK_TESTS=1`). Existe porque `respx` no aplica el reloj de timeout y sin ella el timeout efectivo quedaría sin verificar. CI conserva el cero tráfico saliente. |
