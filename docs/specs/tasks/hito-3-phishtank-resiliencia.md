# Hito 3 — Cliente Asíncrono PhishTank + Resiliencia
## Timeout 4.0s · Caché LRU (TTL 2h) · Fallback elegante

> Repo: `linkguard-backend` · Depende de: Hito 2 (scorer/evidencias) · Bloquea a: Hito 4
> Requisitos núcleo: `RF-401`…`RF-405`, `RNF-101`, `RNF-103`, `RNF-104`

**Objetivo:** integrar la consulta de reputación externa de forma **no bloqueante y resiliente**, con caché volátil en RAM y degradación elegante, garantizando que un fallo de red nunca produzca un error 500 al cliente. Al cerrar el hito, `MATCH_PHISHTANK` suma `+50` y fuerza **Riesgo Alto**, y los estados `available`/`timeout`/`unavailable`/`cached` quedan demostrados.

---

## 3.1 Caché volátil

- [ ] **H3-T01 · Caché LRU con TTL** `[RF-403]` `[RNF-103]`
  - 📄 Crear: `linkguard-backend/app/cache/ttl_lru.py`
  - 🤖 `build`
  - ✅ Estructura LRU en memoria (RAM, sin persistencia) con TTL configurable (`PHISHTANK_TTL_SECONDS=7200`); API `get(key)`, `set(key, value)`, expiración por tiempo; seguro para `asyncio` (un solo event loop). Sin escritura a disco (RNF-103).

## 3.2 Cliente HTTP

- [ ] **H3-T02 · Cliente asíncrono de PhishTank** `[RF-401]` `[RF-402]`
  - 📄 Crear: `linkguard-backend/app/clients/phishtank.py`
  - 🤖 `build`
  - ✅ `httpx.AsyncClient` con `timeout=PHISHTANK_TIMEOUT` (4.0 s) parametrizable; `check_url(url)` consulta la API pública y normaliza la respuesta a un tipo interno (`is_match: bool`, `status: str`). `User-Agent` propio; sin claves en duro.

- [ ] **H3-T03 · Manejo de timeout y errores (fallback)** `[RF-404]`
  - 📄 Modificar: `linkguard-backend/app/clients/phishtank.py`
  - 🤖 `build`
  - ✅ Captura silenciosa de `httpx.TimeoutException` → `status="timeout"`; errores de red / `4xx` / `5xx` → `status="unavailable"`. **Nunca** propaga excepción al handler (cero 500); retorna resultado neutro (`is_match=False`).

- [ ] **H3-T04 · Elevación de riesgo por reputación** `[RF-405]`
  - 📄 Modificar: `linkguard-backend/app/scoring/scorer.py`, `linkguard-backend/app/scoring/evidence.py`
  - 🤖 `build`
  - ✅ Si `is_match=True`: `+50` con evidencia `MATCH_PHISHTANK` ("Reporte en lista negra de PhishTank") y **forzar** `risk_level="Alto"` aunque el score léxico sea bajo. Caso `TC-RF-401`; no match no suma (`TC-RF-402`).

## 3.3 Orquestación concurrente

- [ ] **H3-T05 · Orquestador de análisis concurrente** `[RF-401]`
  - 📄 Crear: `linkguard-backend/app/services/analyzer.py`
  - 🤖 `build`
  - ✅ `analyze_url(url)` ejecuta en paralelo `asyncio.gather(run_rules(...), phishtank.check_url(...))`; mide `execution_time_ms`; combina score léxico + reputación; propaga `phishtank_status` a la respuesta.

- [ ] **H3-T06 · Conectar orquestador al endpoint** `[RF-401]`
  - 📄 Modificar: `linkguard-backend/app/api/v1/analyze.py`
  - 🤖 `build`
  - ✅ El endpoint usa `services.analyzer.analyze_url`; respuesta mantiene el contrato §6 e incorpora `phishtank_status` real. Siempre `HTTP 200` ante fallos de reputación (`TC-RF-403`, `TC-RF-404`).

## 3.4 Pruebas de resiliencia y aislamiento

- [ ] **H3-T07 · Tests unitarios de la caché** `[RF-403]`
  - 📄 Crear: `linkguard-backend/tests/unit/test_cache.py`
  - 🤖 `tester`
  - ✅ hit/miss; expiración por TTL; `TC-RF-405` (misma URL 2 veces en < 2 h → recuperación inmediata `< 1 ms`, `status="cached"`).

- [ ] **H3-T08 · Tests de integración con `respx` (mocks estrictos)** `[RF-401]`…`[RF-405]`
  - 📄 Crear: `linkguard-backend/tests/integration/test_phishtank_resilience.py`
  - 🤖 `tester`
  - ✅ `TC-RF-401` (200 ms, encontrada → +50 y Alto), `TC-RF-402` (no encontrada → solo léxico), `TC-RF-403` (delay > 4 s → `timeout` + HTTP 200), `TC-RF-404` (HTTP 503 → `unavailable` + HTTP 200). **Prohibido** tráfico real saliente.

- [ ] **H3-T09 · Test de aislamiento absoluto de red** `[RNF-101]`
  - 📄 Crear: `linkguard-backend/tests/integration/test_network_isolation.py`
  - 🤖 `tester`
  - ✅ Guard de sockets / `respx` que falla si se intenta conectar al host de la URL analizada (`TC-RNF-101`): cero peticiones a `scheme://netloc` del input.

- [ ] **H3-T10 · Verificación stateless y de memoria** `[RNF-103]` `[RNF-104]`
  - 📄 Crear: `linkguard-backend/tests/integration/test_stateless.py`
  - 🤖 `tester`
  - ✅ `TC-RNF-103`: cero archivos creados/modificados durante una request; `TC-RNF-104`: chequeo documentado de RAM del contenedor `≤ 256 MB` (`docker stats`, script o procedimiento).

- [ ] **H3-T11 · Auditoría de seguridad del Hito 3**
  - 🤖 `security-auditor`
  - ✅ REVISAR: ausencia de SSRF (nunca pedir la URL del usuario), timeout efectivo, sin credenciales/API keys en duro, manejo de errores sin fuga de trazas, `pip-audit` sin high/critical (o con riesgo aceptado y documentado).

### Criterios de salida del Hito 3
- [ ] `TC-RF-401`…`405` en verde con mocks (sin red real).
- [ ] Cualquier fallo de PhishTank devuelve `HTTP 200` con `phishtank_status` `timeout`/`unavailable`.
- [ ] `MATCH_PHISHTANK` (+50) fuerza Riesgo Alto.
- [ ] `TC-RNF-101` (aislamiento) y `TC-RNF-103` (stateless) verificados.
