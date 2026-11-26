# Hito 1 — Backend Core Setup & Schemas
## FastAPI · DTOs Pydantic · Normalizador

> Repo: `linkguard-backend` · Depende de: — · Bloquea a: Hito 2, Hito 4
> Requisitos núcleo: `RF-101`…`RF-105`, `RNF-103`, `RNF-105`, `RNF-106`

**Objetivo:** dejar en pie el esqueleto del servicio FastAPI, el contrato de datos (§6 de requisitos), el pipeline de normalización sintáctica y las bases de observabilidad, seguridad (CORS + rate limit) y containerización. Al cerrar el hito, el endpoint `POST /api/v1/analyze` responde el contrato con `score = 0` (sin reglas aún) y el contrato queda **congelado** para el frontend.

---

## 1.1 Estructura e inicialización del repo

- [x] **H1-T01 · Scaffold del repo backend** `[RNF-103]`
  - 📄 Crear: `linkguard-backend/{app/__init__.py, app/api/__init__.py, app/schemas/__init__.py, app/core/__init__.py, app/normalization/__init__.py, app/engine/__init__.py, app/scoring/__init__.py, app/clients/__init__.py, app/cache/__init__.py, app/services/__init__.py, tests/__init__.py, tests/unit/__init__.py, tests/integration/__init__.py}`
  - 📄 Crear: `linkguard-backend/requirements.txt`, `requirements-dev.txt`, `pyproject.toml` (metadatos + config `ruff`), `.gitignore`, `README.md`
  - 🤖 `build`
  - ✅ Layout de capas coherente con `linkguard-especificacion-arquitectura-v1.md`; `ruff check .` sin hallazgos; dependencias base: `fastapi`, `uvicorn[standard]`, `pydantic`, `pydantic-settings`, `httpx`, `slowapi`, `publicsuffix2` (dev: `pytest`, `pytest-cov`, `pytest-asyncio`, `respx`, `ruff`, `bandit`, `pip-audit`).

## 1.2 Configuración e infraestructura de entrada

- [x] **H1-T02 · Settings centralizados** `[RNF-106]`
  - 📄 Crear: `linkguard-backend/app/core/config.py` (canónico) y `linkguard-backend/app/config.py` (reexporte de compatibilidad)
  - 📄 Crear: `linkguard-backend/.env.example`
  - 🤖 `build`
  - ✅ `Settings(BaseSettings)` con: `ENVIRONMENT`, `PORT`, `CORS_ORIGINS`, `PHISHTANK_TIMEOUT=4.0`, `PHISHTANK_TTL_SECONDS=7200`, `RATE_LIMIT_PER_MINUTE=30`, `PHISHTANK_API_URL`. Ningún valor sensible en duro; `.env` en `.gitignore`.

- [x] **H1-T03 · DTOs Pydantic del contrato de API** `[RF-101]` `[RF-105]`
  - 📄 Crear: `linkguard-backend/app/schemas/analyze.py`
  - 🤖 `build`
  - ✅ `AnalyzeRequest(url: str)` con `min_length=3, max_length=4096`; `AnalyzeResponse(url_analyzed, normalized_url, score: int, risk_level: RiskLevel, recommendation: str, evidences: list[EvidenceDTO], phishtank_status: PhishtankStatus, execution_time_ms: float)`; `EvidenceDTO(rule_id, points, title, description)` (alias `Evidence`); enums `RiskLevel {Bajo, Medio, Alto}` y `PhishtankStatus {available, timeout, unavailable, cached}`. OpenAPI refleja exactamente el contrato §6.

- [x] **H1-T04 · Modelos internos + registro de pesos** `[RF-301]`
  - 📄 Crear: `linkguard-backend/app/engine/models.py`, `linkguard-backend/app/engine/weights.py`
  - 🤖 `build`
  - ✅ `ParsedURL` (scheme, netloc, host, port, path, params, query, fragment, normalized_url) y `RuleResult(rule_id, activated, points, title, description)`. `weights.py` con la matriz exacta: `MATCH_PHISHTANK=50, F02=25, F06=20, F08=20, F11=15, F05=15, F04=15, F09=10, F03=10, F01=10, F07=8, F10=7`.

## 1.3 Normalizador (Módulo 100)

- [x] **H1-T05 · Errores estructurados** `[RF-105]`
  - 📄 Crear: `linkguard-backend/app/core/errors.py`
  - 🤖 `build`
  - ✅ Excepción `URLTooLongError` / `InvalidURLError` mapeables a `HTTP 400` con mensaje `"URL excede la longitud máxima procesable (4096 caracteres)"` y `"La entrada no corresponde a un enlace válido"` (es-419).

- [x] **H1-T06 · Normalizador sintáctico** `[RF-101]` `[RF-102]` `[RF-103]` `[RF-104]` `[RF-105]`
  - 📄 Crear: `linkguard-backend/app/normalization/normalizer.py`
  - 🤖 `build`
  - ✅ `normalize(raw: str) -> ParsedURL` que: (RF-101) `strip` + elimina `\x00-\x1F` y `\x7F`; (RF-102) antepone `http://` si falta esquema; (RF-103) descompone con `urllib.parse` en los 6 componentes; (RF-104) decodifica `%XX` y convierte IDN→Punycode (`xn--`); (RF-105) rechaza > 4096 chars con `URLTooLongError`. Función **pura**, sin red.
  - 🔗 Casos: `TC-RF-101`…`TC-RF-105`, `TC-EDGE-01`, `TC-EDGE-02`, `TC-EDGE-03`, `TC-EDGE-04`.

- [x] **H1-T07 · Tests unitarios del normalizador** `[RF-101]`…`[RF-105]`
  - 📄 Crear: `linkguard-backend/tests/conftest.py`, `linkguard-backend/tests/unit/test_normalizer.py`
  - 🤖 `tester`
  - ✅ Cubre `TC-RF-101` (`"  http://example.com/demo  "` → `"http://example.com/demo"`), `TC-RF-102` (`example.com/login-path` → `http://example.com/login-path`), `TC-RF-103`, `TC-RF-104` (IDN→Punycode), `TC-RF-105` (4097 chars → error), y bordes `TC-EDGE-01`…`04`. Sin red.

## 1.4 Aplicación FastAPI y endpoint

- [x] **H1-T08 · App FastAPI + router v1 + middleware** `[RNF-105]` `[RNF-106]`
  - 📄 Crear: `linkguard-backend/app/main.py`, `linkguard-backend/app/api/v1/__init__.py`, `linkguard-backend/app/api/v1/router.py`
  - 🤖 `build`
  - ✅ `FastAPI` con CORS restringido a `CORS_ORIGINS`; `slowapi` con límite `RATE_LIMIT_PER_MINUTE` por IP (30/min) → `429`; handlers globales que devuelven JSON UTF-8 en es-419 y **no filtran stack traces**; montaje del router bajo `/api/v1`.

- [x] **H1-T09 · Endpoint POST /api/v1/analyze (stub)** `[RF-101]` `[RNF-106]`
  - 📄 Crear: `linkguard-backend/app/api/v1/analyze.py`
  - 🤖 `build`
  - ✅ Recibe `AnalyzeRequest`, llama a `normalize()`, devuelve `AnalyzeResponse` con `score=0`, `risk_level="Bajo"`, `evidences=[]`, `phishtank_status="unavailable"`, `execution_time_ms` real. Maneja `URLTooLongError`/`InvalidURLError` → `400`.
  - 📌 Hito 2 reemplaza el cuerpo por el pipeline real; el **contrato no cambia**.

- [x] **H1-T10 · Observabilidad y endpoint de salud** `[RNF-106]` `[RNF-103]`
  - 📄 Crear: `linkguard-backend/app/core/logging.py`; 📄 Modificar: `linkguard-backend/app/main.py`
  - 🤖 `build`
  - ✅ `GET /health` → `200 {"status":"healthy","service":"linkguard-api","version":"1.0.0","timestamp":...}`; logging estructurado JSON a `stdout` con evento `ANALYZE_EVENT` (campos: `timestamp`, `level`, `event_type`, `url_hash_sha256`, `score`, `risk_level`, `phishtank_status`, `rules_activated_count`, `execution_time_ms`, `client_ip_hash`). **Hashear** URL e IP (SHA-256), nunca loguear la URL cruda.

## 1.5 Empaquetado y CI del backend

- [x] **H1-T11 · Dockerfile multi-stage backend** `[RNF-104]`
  - 📄 Crear: `linkguard-backend/Dockerfile`, `linkguard-backend/.dockerignore`
  - 🤖 `build`
  - ✅ `python:3.12-slim` multi-stage con venv, usuario no-root `appuser` (UID 10001), `HEALTHCHECK` a `/health`, `CMD uvicorn app.main:app`. Imagen final `< 180 MB`.

- [x] **H1-T12 · Pipeline CI backend** `[RNF-105]`
  - 📄 Crear: `linkguard-backend/.github/workflows/backend-ci.yml`
  - 🤖 `build`
  - ✅ Jobs: `lint-and-sast` (`ruff check .`, `bandit -r ./app -ll`, `pip-audit`) → `test` (`pytest --cov=app --cov-fail-under=80`) → `docker-build` (build sin push).

## 1.6 Verificación y auditoría del hito

- [x] **H1-T13 · Tests de integración de la capa HTTP** `[RNF-105]` `[RF-105]`
  - 📄 Crear: `linkguard-backend/tests/integration/test_analyze_endpoint.py`, `linkguard-backend/tests/integration/test_rate_limit.py`
  - 🤖 `tester`
  - ✅ `/health` 200; `analyze` con URL válida 200; URL > 4096 → 400; `url` < 3 → 422; petición 31 en < 1 min → 429 (`TC-RNF-105`); CORS restringido (origen no permitido rechazado). Usar `httpx.ASGITransport`, **sin red real**.

- [x] **H1-T14 · Auditoría de seguridad del Hito 1**
  - 🤖 `security-auditor`
  - ✅ Dictamen APROBADO/RECHAZADO sobre: CORS restrictivo, rate limiting activo, ausencia de secretos en duro, ausencia de peticiones a la URL analizada (RNF-101), mensajes de error sin fuga de datos.

### Criterios de salida del Hito 1
- [ ] `POST /api/v1/analyze` responde el contrato §6 (con `score=0`) y `GET /health` responde 200.
- [ ] Normalizador cubierto por `TC-RF-101`…`105` y `TC-EDGE-01`…`04`.
- [ ] Imagen Docker construye y la CI pasa (lint + SAST + tests ≥ 80%).
- [ ] Contrato de API **congelado** (commit etiquetado `v0.1.0-contract`).
