# Hito 5 — Precisión y Robustez del Motor (Motor v3)
## Reputación local · Clasificador léxico lineal · Scoring v3 · Evaluación reproducible

> Repo: `linkguard-backend` · Depende de: Hito 3 (PhishTank/resiliencia) · Contrato de API **congelado** (`v0.1.0-contract`)
> Spec: `docs/specs/linkguard-especificacion-accuracy-v3.md` · Referencia: `docs/specs/accuracy-lab/` (RESULTS.md, scripts de laboratorio)
> Requisitos núcleo: `RF-501`…`RF-606`, `RF-701`…`RF-706`, `RF-801`…`RF-805`, `RNF-107`…`RNF-111` (condicional: `RF-901`)

**Objetivo:** pasar de Recall 1.9 % (medido sobre JPCERT + Phishing.Database) a ≥ 92 % con FPR ≤ 3 % sin tocar el frontend ni el contrato, manteniendo `≤ 50 ms`, `≤ 256 MB`, costo $0 y las 5 reglas inviolables de `AGENTS.md`.

> **Orden obligatorio:** T01 → T02/T03 → T04 → (T05, T08 en paralelo lógico) → T06/T07 → T09 → T10 → T11 → T12/T13 → T14/T15 → T16 → (T17 opcional). T04 va **antes** de entrenar (T09): el PSL cambia los vectores de características.

---

## 5.0 Especificación y línea base

- [x] **H5-T01 · Consolidar specs v3 y actualizar AGENTS.md** `[RF-501]…[RF-901]`
  - 📄 Crear: `docs/specs/linkguard-especificacion-accuracy-v3.md` (copiar adendo), `docs/specs/accuracy-lab/` (descomprimir el zip de referencia); 📄 Modificar: `AGENTS.md` (mapa de specs + hito 5; aclarar RNF-101/RNF-103 según adendo §3; regla de artefactos de solo lectura; regla "ML solo lineal, sin dependencias de entrenamiento en `requirements.txt`")
  - 🤖 `build`
  - ✅ Specs referenciadas en el mapa de `AGENTS.md`; unificar la inconsistencia 500/500 vs 1 000/1 000 apuntando al protocolo del adendo §7. Sin cambios de código.

- [x] **H5-T02 · Harness de evaluación y línea base v2** `[RF-605]` `[§7]`
  - 📄 Crear: `scripts/ml/fetch_data.py`, `scripts/ml/build_dataset.py`, `scripts/ml/evaluate.py`, `requirements-ml.txt`, `docs/reports/accuracy-baseline-v2.md`
  - 🤖 `build`
  - ✅ Descarga JPCERT, Phishing.Database, Tranco (ID fijo; alternativa documentada zer0h) y Citizen Lab; construye datasets con cap de 3 URLs/dominio; ejecuta el motor v2 **en proceso** (sin HTTP) y reproduce la línea base (Recall ≈ 2 %, F1 ≈ 0.04 sobre las muestras del laboratorio). Informe con particiones agrupada, cruzada y temporal. Semillas fijas; manifiesto con SHA-256.

- [x] **H5-T03 · Benchmark contra la API (humo)** `[§7]`
  - 📄 Crear: `scripts/benchmark_api.py`
  - 🤖 `build`
  - ✅ Modo `--local` (ASGI en proceso, rate limit alto) y modo `--remote` (≤ 300 URLs, respeta 30 req/min); guarda CSV `url_hash, score, nivel, phishtank_status`. **Nunca** guarda URLs en claro en logs del servidor.

## 5.1 Reputación local

- [x] **H5-T04 · PSL vigente** `[RF-501]`
  - 📄 Crear: `app/normalization/psl.py`, `app/engine/data/public_suffix_list.dat`; 📄 Modificar: `app/engine/rules/f03_*.py`, `f07_*.py`, `requirements.txt` (retirar `publicsuffix2` si se reemplaza)
  - 🤖 `build`
  - ✅ API `registrable_domain(host)` / `public_suffix(host)` con ICANN+PRIVATE; `TC-RF-501-01`; **todos los tests F03/F07 existentes siguen en verde**.

- [x] **H5-T05 · Generador de artefactos de reputación** `[RF-502]` `[RF-503]` `[RF-504]` `[RF-505]`
  - 📄 Crear: `scripts/ml/build_reputation_artifacts.py`, `app/engine/data/abusable_services.py`, `app/engine/data/reputation/manifest.json` (+ `allowlist_top100k.txt`, `blocklist_urls.bin`, `blocklist_hosts.bin`)
  - 🤖 `build`
  - ✅ Allowlist excluye sufijos públicos y servicios abusables; blocklists = hashes `blake2b-64` ordenados; **verificar y registrar** cuáles feeds (Phishing.Database, OpenPhish, URLhaus, PhishTank con key) están realmente accesibles; los no disponibles se documentan, no bloquean. Tamaño total ≤ 15 MB.

- [x] **H5-T06 · Módulo runtime de reputación** `[RF-502]` `[RF-504]` `[RF-506]` `[RNF-107]`
  - 📄 Crear: `app/reputation/__init__.py`, `allowlist.py`, `blocklist.py`, `loader.py`
  - 🤖 `build`
  - ✅ Carga al arranque en `array('Q')`; `bisect`; verificación SHA-256 contra manifiesto; arranque degradado si falla; sin escrituras en disco; `get_reputation(parsed) -> ReputationSignals(allowlisted, abusable, feed_url, feed_host)`.

- [x] **H5-T07 · Workflow semanal de refresco** `[RF-505]` `[RNF-107]`
  - 📄 Crear: `.github/workflows/refresh-reputation.yml`; 📄 Modificar: `Dockerfile` (COPY de artefactos solo lectura), `.dockerignore`
  - 🤖 `build`
  - ✅ `schedule` semanal + `workflow_dispatch`; abre PR con artefactos y manifiesto; el redeploy usa el flujo existente; imagen final < 220 MB; sin secretos en duro (la app key opcional de PhishTank, si existe, va en GitHub Secrets).

## 5.2 Clasificador léxico

- [x] **H5-T08 · Featurizador determinista** `[RF-601]` `[RNF-110]`
  - 📄 Crear: `app/ml/__init__.py`, `app/ml/features.py`, `app/engine/data/brands.py`, `scripts/ml/gen_brands.py`, `tests/unit/ml/test_features.py`, `tests/data/golden_vectors.json`
  - 🤖 `build` → `tester`
  - ✅ Portar `accuracy-lab/scripts/feat2.py` (`rules=False`) con type hints/docstrings es-419; hash `zlib.crc32`; sin ReDoS; `TC-RF-601-01` con 20 vectores congelados (generados **después** de T04).

- [x] **H5-T09 · Pipeline de entrenamiento y exportación** `[RF-602]` `[RF-603]` `[RF-605]` `[RF-606]` `[RNF-108]`
  - 📄 Crear: `scripts/ml/train.py`, `scripts/ml/export_model.py`, `tests/data/hard_negatives.txt` (≥ 200), `app/engine/data/model_v1.json`
  - 🤖 `build`
  - ✅ Regresión logística (`class_weight=balanced`, `C=3`, `liblinear`); umbrales `t_medio` (FPR ≤ 3 %) y `t_alto` (FPR ≤ 1 %) sobre negativos retenidos; manifiesto de datos en el JSON; JSON ≤ 3 MB; reproducible con la misma semilla. Informe `docs/reports/accuracy-model-v1.md` con las 4 particiones.

- [x] **H5-T10 · Inferencia y explicabilidad** `[RF-602]` `[RF-604]` `[RNF-109]`
  - 📄 Crear: `app/ml/model.py`, `app/ml/explain.py`, `tests/unit/ml/test_model.py`
  - 🤖 `build` → `tester`
  - ✅ `predict(url) -> float`; `explain(url) -> dict[grupo, float]`; carga única al arranque; `TC-RF-602-01` (paridad < 1e-3 con referencia); latencia ≤ 1 ms/URL; falla de artefacto → modo sin modelo (HTTP 200).

## 5.3 Scoring v3 e integración

- [x] **H5-T11 · Scorer v3 + evidencias ML** `[RF-701]`…`[RF-706]`
  - 📄 Modificar: `app/scoring/scorer.py`, `app/scoring/evidence.py`; 📄 Crear: `app/scoring/calibration.py`
  - 🤖 `build`
  - ✅ Implementa §5 del adendo (PL, `max`, reparto de puntos por mayor resto, allowlist cap, pisos de nivel); **`TC-RF-301…305` y `TC-RF-401…406` siguen en verde** (inyectando allowlist vacía donde haga falta); `TC-RF-704-01`, `TC-RF-705-01`.

- [x] **H5-T12 · Orquestación y feeds en el analizador** `[RF-803]` `[RF-804]` `[RF-805]`
  - 📄 Modificar: `app/services/analyzer.py`; 📄 Crear: `tests/integration/test_analyze_v3.py`
  - 🤖 `build` → `tester`
  - ✅ `asyncio.gather(léxico+modelo+reputación local, PhishTank)`; contrato idéntico (snapshot del esquema OpenAPI antes/después); degradación elegante por componente; `TC-RF-504-01`, `TC-RF-506-01`, `TC-RF-804-01`.

- [x] **H5-T13 · PhishTank: variantes, app key opcional y verificación real** `[RF-801]` `[RF-802]` — **implementado y probado con respx**; verificación live C6 bloqueada por HTTP 429 del tercero sin `PHISHTANK_APP_KEY`, documentado en `docs/reports/c6-live-verification.md`
  - 📄 Modificar: `app/clients/phishtank.py`, `app/core/config.py`, `.env.example`; 📄 Crear: `tests/integration/test_phishtank_variants.py`, `scripts/verify_phishtank_live.py` (opt-in)
  - 🤖 `build` → `tester`
  - ✅ Variantes original/normalizada/barra final dentro del timeout global de 4.0 s; `PHISHTANK_APP_KEY` opcional por `BaseSettings`; `respx` en CI (`TC-RF-801-01`); el script opt-in (`LINKGUARD_LIVE_TESTS=1`) confirma o descarta la hipótesis C6 con URLs reales de PhishTank y reporta tasa de acierto por variante y rate limits. **Documentar el resultado en el informe.**

## 5.4 Pruebas, evaluación y auditoría

- [x] **H5-T14 · Suite de pruebas v3** `[RNF-102]` `[RNF-104]` `[RNF-110]`
  - 📄 Crear: `tests/unit/test_reputation.py`, `tests/unit/test_scorer_v3.py`, `tests/integration/test_hard_negatives.py`, `tests/unit/test_performance_v3.py`
  - 🤖 `tester`
  - ✅ `TC-EVAL-01` (0/≥200 difíciles Medio/Alto), `TC-RNF-102-v3` (p95 ≤ 50 ms), `TC-RNF-104-v3` (RAM ≤ 256 MB con artefactos), `TC-RF-502-02`, `TC-RF-503-01`; cobertura ≥ 80 %.
  - **H5-T14b (opcional):** reevaluar F04 con umbral por longitud; solo si mejora la ablación y no rompe `TC-F04-*`.

- [x] **H5-T15 · Evaluación final y guardia de regresión** `[§7]`
  - 📄 Crear: `docs/reports/accuracy-v3.md`, `tests/data/mini_benchmark.tsv` (400 URLs congeladas), `tests/integration/test_regression_benchmark.py`
  - 🤖 `build`
  - ✅ KPIs del adendo §7 con las 4 particiones, ablación (solo reglas / +modelo / +allowlist / +feeds), curva Recall@FPR y declaración explícita de las limitaciones (§1.2, §10). `TC-EVAL-02` en CI.

- [x] **H5-T16 · Auditoría de seguridad del Hito 5**
  - 🤖 `security-auditor`
  - ✅ REVISAR: RNF-101 (cero tráfico a la URL analizada), ReDoS en featurizador/parsers, integridad de artefactos y arranque degradado, cadena de suministro de feeds (descarga solo en CI, límites de tamaño, sin `pickle`/`eval`), secretos, logs sin URL/dominio en claro, `pip-audit`/`bandit` limpios. Dictamen APROBADO/RECHAZADO con observaciones.

## 5.5 Condicional

- [x] **H5-T17 · (Opcional) Edad de dominio vía RDAP** `[RF-901]` — **medido y rechazado (2026-11-26)**
  - 📄 Creados: `scripts/ml/measure_rdap_gain.py`, `tests/unit/test_measure_rdap_gain.py`, `docs/reports/rdap-experiment.md`
  - 📄 **No creado:** `app/clients/rdap.py` (la compuerta no se cumple)
  - 🤖 `build` → `tester`
  - ✅ **Primero se mide, luego se decide.** Resultado: Δ recall **+0,00 pp** a FPR ≤ 3 % (0,959 → 0,959; umbral 31 en ambos casos) sobre 1 599 dominios (799 positivos / 800 negativos) con solo 4 positivos nuevos (< 30 días). p95 total **269 ms** (cumple) pero la mejora de recall no alcanza los 3 pp. Solo el 0,5 % de los positivos del corpus congelado era reciente; `vgydea.com` tiene 1 440 días. Se documenta como experimento negativo; `ENABLE_RDAP` **no se añade** y la allowlist/umbrales quedan intactos. Reabrir solo con feeds de phishing fresco. Ver `docs/reports/rdap-experiment.md`.

---

### Criterios de salida del Hito 5
- [x] Contrato `POST /api/v1/analyze` idéntico (diff de OpenAPI vacío) y `GET /health` 200.
- [x] KPIs del adendo §7 cumplidos **o** brechas declaradas con causa en `docs/reports/accuracy-v3.md`.
- [x] `TC-EVAL-01`: 0 de ≥ 200 negativos difíciles en Medio/Alto.
- [x] `≤ 50 ms` p95 (3,638 ms), `≤ 256 MB` (205,18 MB servicio), imagen 71,26 MB comprimida, CI verde (ruff, bandit, pip-audit): **707 pruebas pasan, 3 omitidas, cobertura 92,59 %** (`pytest -q`, `--cov-fail-under=80`).
- [x] Dictamen de seguridad H5-T16 APROBADO (reauditoría independiente).
- [x] Notas de Obsidian actualizadas por tarea (decisiones, deuda técnica, métricas).
