# Hito 2 — Motor de Reglas Léxicas (F01–F11) + Tests Unitarios
## Pipeline de funciones puras · Scoring · Explicabilidad

> Repo: `linkguard-backend` · Depende de: Hito 1 (ParsedURL, RuleResult, contrato) · Bloquea a: Hito 3
> Requisitos núcleo: `RF-201`…`RF-211`, `RF-301`…`RF-304`, `RNF-102`

**Objetivo:** implementar las 11 funciones puras `F01`–`F11` (una por archivo), su registro, el pipeline determinista, el cálculo ponderado con tope de 100, el mapeo de niveles y el desglose de evidencias/recomendaciones. Al cerrar el hito, el endpoint ya calcula riesgo léxico real (sin PhishTank) y el scoring queda demostrado por los casos `TC-RF-301`…`305`.

> **Regla por regla:** firma única `evaluate_<nombre>(parsed: ParsedURL) -> RuleResult`. Sin red, sin estado, con `type hints` y docstring es-419. El `rule_id` y `points` deben coincidir con `weights.py` y con la matriz §3 de requisitos.

---

## 2.1 Las 11 funciones puras (una tarea = una regla)

- [x] **H2-T01 · F01 — Longitud excesiva** `[RF-201]`
  - 📄 Crear: `linkguard-backend/app/engine/rules/f01_excessive_length.py`
  - 🤖 `build`
  - ✅ `True` si longitud normalizada `≥ 75` → `F01_EXCESSIVE_LENGTH`, `+10`. Casos `TC-F01-P` (80 chars → True/+10) y `TC-F01-N` (45 chars → False/0).

- [x] **H2-T02 · F02 — Dirección IP directa** `[RF-202]`
  - 📄 Crear: `linkguard-backend/app/engine/rules/f02_direct_ip.py`
  - 🤖 `build`
  - ✅ `netloc` sin puerto es IPv4 (decimal/octal/hex) o IPv6 (librería `ipaddress`; normalizar octal/hex a decimal, `R-EDGE-03`) → `F02_DIRECT_IP`, `+25`. Caso `TC-F02-P` (`10.0.0.1` → True/+25).

- [x] **H2-T03 · F03 — Subdominios múltiples** `[RF-203]`
  - 📄 Crear: `linkguard-backend/app/engine/rules/f03_multiple_subdomains.py`
  - 🤖 `build`
  - ✅ Extrae dominio raíz + TLD con **Public Suffix List** (`publicsuffix2`) y cuenta niveles restantes; `True` si `≥ 3` → `F03_MULTIPLE_SUBDOMAINS`, `+10`. Caso `TC-F03-P`.

- [x] **H2-T04 · F04 — Entropía de Shannon del host** `[RF-204]`
  - 📄 Crear: `linkguard-backend/app/engine/rules/f04_shannon_entropy.py`
  - 🤖 `build`
  - ✅ `H(X) = -Σ p(x)·log2 p(x)` sobre el host; `True` si `> 4.5` bits/símbolo → `F04_SHANNON_ENTROPY`, `+15`. Caso `TC-F04-P` (H=4.8).

- [x] **H2-T05 · F05 — Acortador de URL** `[RF-205]`
  - 📄 Crear: `linkguard-backend/app/engine/rules/f05_url_shortener.py`, `linkguard-backend/app/engine/data/url_shorteners.py`
  - 🤖 `build`
  - ✅ `hashset` estático de acortadores conocidos; `True` si el host normalizado coincide (o subdominio de uno listado) → `F05_URL_SHORTENER`, `+15`. Caso `TC-F05-P`.

- [x] **H2-T06 · F06 — Símbolo `@`** `[RF-206]`
  - 📄 Crear: `linkguard-backend/app/engine/rules/f06_at_symbol.py`
  - 🤖 `build`
  - ✅ `True` si `@` aparece en host o path → `F06_AT_SYMBOL`, `+20`. Caso `TC-F06-P`; soporta múltiples `@` (`TC-EDGE-04`).

- [x] **H2-T07 · F07 — Guiones en el dominio** `[RF-207]`
  - 📄 Crear: `linkguard-backend/app/engine/rules/f07_hyphens_in_domain.py`
  - 🤖 `build`
  - ✅ Cuenta `-` en el **nombre del dominio principal**; `True` si `≥ 2` → `F07_HYPHENS_IN_DOMAIN`, `+8`. Caso `TC-F07-P`.

- [x] **H2-T08 · F08 — Desvío de esquema en path/query** `[RF-208]`
  - 📄 Crear: `linkguard-backend/app/engine/rules/f08_schema_redirect.py`
  - 🤖 `build`
  - ✅ `True` si `http:` o `https:` aparece dentro de `path` o `query` → `F08_SCHEMA_REDIRECT`, `+20`. Caso `TC-F08-P`.

- [x] **H2-T09 · F09 — Puerto no estándar** `[RF-209]`
  - 📄 Crear: `linkguard-backend/app/engine/rules/f09_non_standard_port.py`
  - 🤖 `build`
  - ✅ `True` si `netloc` incluye puerto explícito ∉ {80, 443} → `F09_NON_STANDARD_PORT`, `+10`. Caso `TC-F09-P`.

- [x] **H2-T10 · F10 — Ratio de caracteres especiales** `[RF-210]`
  - 📄 Crear: `linkguard-backend/app/engine/rules/f10_special_chars_ratio.py`
  - 🤖 `build`
  - ✅ `count(?, =, %, -, _, &) / len(url)`; `True` si `> 0.15` → `F10_SPECIAL_CHARS_RATIO`, `+7`. Caso `TC-F10-P`.

- [x] **H2-T11 · F11 — Palabras clave sensibles** `[RF-211]`
  - 📄 Crear: `linkguard-backend/app/engine/rules/f11_social_engineering_keywords.py`, `linkguard-backend/app/engine/data/sensitive_keywords.py`
  - 🤖 `build`
  - ✅ Coincidencia case-insensitive de `login, bank, verify, account, update, secure, signin, service` en host/path/query → `F11_SOCIAL_ENGINEERING_KEYWORDS`, `+15`. Caso `TC-F11-P`.

## 2.2 Registro y pipeline

- [x] **H2-T12 · Registro de reglas** `[RF-301]`
  - 📄 Crear: `linkguard-backend/app/engine/rules/__init__.py`, `linkguard-backend/app/engine/rules/registry.py`
  - 🤖 `build`
  - ✅ `RULES: list[Rule]` con las 11 funciones puras en orden determinista; cada `Rule` expone `rule_id`, `points`, `title` y `description` (es-419) alineados con `weights.py`.

- [x] **H2-T13 · Pipeline de evaluación** `[RF-301]`
  - 📄 Crear: `linkguard-backend/app/engine/pipeline.py`
  - 🤖 `build`
  - ✅ `run_rules(parsed: ParsedURL) -> list[RuleResult]` que ejecuta las 11 reglas y devuelve solo las activadas (o todas con `activated`). Función pura y determinista, `≤ 50 ms` (`TC-RNF-102`).

## 2.3 Scoring, clasificación y explicabilidad (Módulo 300)

- [x] **H2-T14 · Cálculo ponderado y mapeo de niveles** `[RF-301]` `[RF-302]`
  - 📄 Crear: `linkguard-backend/app/scoring/scorer.py`
  - 🤖 `build`
  - ✅ `score = min(100, Σ wᵢ·fᵢ)`, redondeado; mapeo Bajo `0–30`, Medio `31–69`, Alto `70–100`. Casos `TC-RF-301` (0 → Bajo), `TC-RF-302` (F01+F11=25 → Bajo), `TC-RF-303` (F02+F08=45 → Medio), `TC-RF-304` (80 → Alto), `TC-RF-305` (125 teórico → 100 → Alto).

- [x] **H2-T15 · Evidencias granulares** `[RF-303]` `[RNF-106]`
  - 📄 Crear: `linkguard-backend/app/scoring/evidence.py`
  - 🤖 `build`
  - ✅ Convierte `RuleResult` activos en `Evidence(rule_id, points, title, description)`: `rule_id` (ej. `F02_DIRECT_IP`), `points`, `title` técnico y `description` comprensible es-419.

- [x] **H2-T16 · Recomendaciones por nivel** `[RF-304]` `[RNF-106]`
  - 📄 Crear: `linkguard-backend/app/scoring/recommendations.py`
  - 🤖 `build`
  - ✅ Texto **exacto** especificado para Bajo / Medio / Alto (ver requisitos §RF-304), sin cambios de redacción.

## 2.4 Integración y pruebas

- [x] **H2-T17 · Integrar pipeline + scorer en el endpoint** `[RF-301]`…`[RF-304]`
  - 📄 Modificar: `linkguard-backend/app/api/v1/analyze.py`
  - 🤖 `build`
  - ✅ `analyze` ejecuta `normalize` → `run_rules` → `scorer` → arma `evidences` + `recommendation`; `phishtank_status="unavailable"` (se conecta en Hito 3). **No cambia el contrato.**

- [x] **H2-T18 · Tests unitarios F01–F11** `[RF-201]`…`[RF-211]`
  - 📄 Crear: `linkguard-backend/tests/unit/rules/test_f01.py` … `test_f11.py`
  - 🤖 `tester`
  - ✅ Un test positivo por regla (`TC-F0n-P` → `True`/`+puntos`) y, donde aplique, un negativo (`TC-F01-N`). Verifica `rule_id`, `activated` y `points`.

- [x] **H2-T19 · Tests de scoring, clasificación y bordes** `[RF-301]`…`[RF-305]` `[R-EDGE]`
  - 📄 Crear: `linkguard-backend/tests/unit/test_pipeline.py`, `linkguard-backend/tests/unit/test_scorer.py`
  - 🤖 `tester`
  - ✅ `TC-RF-301`…`305`; verifica tope 100 y fronteras 30/31 y 69/70; evidencias y recomendación asociada.

- [x] **H2-T20 · Test de latencia local** `[RNF-102]`
  - 📄 Crear: `linkguard-backend/tests/unit/test_performance.py`
  - 🤖 `tester`
  - ✅ Mide `time.perf_counter()` de `run_rules` + scoring sobre una URL; asevera `≤ 50 ms` (`TC-RNF-102`).

- [x] **H2-T21 · Auditoría de seguridad del Hito 2**
  - 🤖 `security-auditor`
  - ✅ REVISAR: reglas puras sin red (RNF-101); regex sin ReDoS (F11/F08); ausencia de `eval`/`exec`; manejo seguro de entradas Unicode/Punycode; sin dependencias no autorizadas.

### Criterios de salida del Hito 2
- [x] Las 11 reglas implementadas, registradas y cubiertas por tests (`TC-F01`…`TC-F11`).
- [x] Scoring `TC-RF-301`…`305` en verde (incluido tope 100).
- [x] Endpoint devuelve `score`, `risk_level`, `evidences` y `recommendation` reales.
- [x] Latencia local `≤ 50 ms` demostrada; cobertura backend `≥ 80%`.
