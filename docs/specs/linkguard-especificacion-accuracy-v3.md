# ADENDO DE ESPECIFICACIÓN v3 — PRECISIÓN Y ROBUSTEZ DEL MOTOR (Accuracy)
## Proyecto: LinkGuard — Sistema Automatizado para la Evaluación de Riesgo de URLs
**Enfoque:** Specification-Driven Development (SDD)
**Estado:** Borrador para aprobación — Hito 5
**Complementa a:** `linkguard-especificacion-requisitos-v2.md` (permanece vigente salvo lo que este adendo reemplaza expresamente)
**Evidencia de soporte:** `accuracy-lab/RESULTS.md` (mediciones reproducibles del 24-nov-2026)
**Contrato de API:** **INVARIANTE** (§6 de requisitos v2). El frontend no cambia.

---

## 1. DIAGNÓSTICO MEDIDO (LÍNEA BASE DEL MOTOR v2)

Medición sobre el motor léxico v2 sin PhishTank, con 4 800 URLs de phishing (2 400 JPCERT estratificadas 2019-2026 + 2 400 de Phishing.Database) y 3 048 negativos (top-10k, Citizen Lab con rutas reales, 48 logins legítimos "difíciles").

| Fuente | n | Bajo | Medio | Alto |
| :-- | --: | --: | --: | --: |
| JPCERT | 2 400 | 98.4 % | 1.5 % | 0.1 % |
| Phishing.Database (global) | 2 400 | 97.8 % | 2.0 % | 0.2 % |
| Negativos (top-10k / Citizen Lab / difíciles) | 3 048 | ≈ 99.9 % | ≈ 0.1 % | 0 |

**Resultado global:** TP=90, FN=4 710, FP=3, TN=3 045 → **Recall 1.9 %, Precision 96.8 %, F1 0.037**. El 69.7 % de las URLs de JPCERT obtiene score = 0. El problema **no es regional** (Phishing.Database global falla igual).

### 1.1 Causas raíz

| ID | Causa | Evidencia |
| :-- | :-- | :-- |
| C1 | **Techo estructural de recall**: suma de señales débiles; Alto exige ≥70 y un phishing típico activa 0-3 reglas. | 98.4 % Bajo; reglas F04 y F09 nunca se activaron; F06 < 0.1 %. |
| C2 | Reglas pensadas para phishing "de manual" (IP, `@`, puerto). El phishing real es **sin marca**, con dominios aleatorios (`ybrjaouww.com`), TLD baratos (`.cn`, `.top`, `.shop`), DDNS y plataformas abusadas (`workers.dev`). | Muestras de score 0 en `RESULTS.md`; análisis de JPCERT/Macnica. |
| C3 | **Sin reputación positiva**: `login`/`signin` suma F11 sin considerar el dominio. | 2/48 logins legítimos ya marcados Medio (F11+F08+F01=45); un clasificador sin allowlist marca 36-42/48. |
| C4 | **PSL de 2019** (`publicsuffix2==2.20191221`) trata `vercel.app`, `pages.dev`, `netlify.app`, `r2.dev`, `replit.app`, `framer.app`, `webflow.io` como un único dominio registrable. | Rompe F03/F07 y haría que una allowlist ingenua deje pasar todo un hosting. |
| C5 | **Feeds**: cobertura de hosts históricos de JPCERT 0.1 %-6.1 %; contienen dominios legítimos de alto ranking (`mercadolibre.com.ar`, `pastebin.com`). | Útiles contra phishing *fresco*, no suficientes; no pueden anular la allowlist. |
| C6 | **Cliente PhishTank** (hipótesis a verificar en H5-T13): consulta la URL ya normalizada (con `http://` inyectado, `%XX` decodificado, punycode) mientras PhishTank empareja URL exacta; sin app key puede caer en rate limit en benchmarks masivos. | Revisión del código `app/clients/phishtank.py`. |
| C7 | F04 (entropía por etiqueta > 4.5) exige ≥ 23 símbolos distintos: casi inalcanzable. | Hallazgo de la sesión de backend; 0 activaciones. |

### 1.2 Mejora potencial medida (prototipo de laboratorio)

| Prueba | AUC | Recall @FPR 1 % | Recall @FPR 3 % |
| :-- | --: | --: | --: |
| Agrupada por dominio | 0.991 | 90 % | 94.5 % |
| Cruzada: PhishDB → JPCERT | 0.973 | 79 % | 86 % |
| Cruzada: JPCERT → PhishDB | 0.961 | 69 % | 80 % |
| Temporal: JPCERT ≤2023 → 2025-26 | 0.987 | 86 % | 92 % |

Con allowlist top-100k: 0/48 logins legítimos difíciles marcados; costo ≤ 0.9 % de positivos. **Límites** (obligatorio declararlos en el informe): negativos de sitios populares; positivos ya dados de baja; no medido FPR sobre sitios legítimos pequeños ni señales de edad de dominio.

---

## 2. DECISIONES DE ARQUITECTURA (ADR)

| ID | Decisión | Justificación |
| :-- | :-- | :-- |
| D1 | **Clasificador lineal interpretable** (regresión logística con hashing), entrenado offline y servido como JSON; inferencia en Python puro. | +0.19 ms/URL, 0 dependencias nuevas, costo $0, explicable por contribuciones aditivas. No es aprendizaje profundo ni LLM. |
| D2 | **Allowlist de reputación con precedencia** sobre señales léxicas y feeds por host; nunca sobre coincidencia exacta de URL en feed confirmado. | Elimina FP de login legítimos con ≤ 0.9 % de costo en recall. |
| D3 | **Feeds compactados en build** (CI), no descargados en runtime; estructura `array('Q')` ordenada + búsqueda binaria. | 9.4 MB vs ≈70 MB con `set`; cold start rápido; respeta RNF-101/103. |
| D4 | **Scoring por combinación `max`** entre reglas v2 y modelo; las reglas v2 son un *piso*, nunca bajan el riesgo. | Conserva TC-RF-301…305 y la explicabilidad existente. |
| D5 | **Contrato y recomendaciones invariantes**; solo se agregan nuevos `rule_id` de evidencia. | Cero trabajo en frontend. |
| D6 | Enriquecimientos remotos (RDAP/edad de dominio) **condicionales y medidos** (H5-T17). | Atacan el residuo de dominios aleatorios cortos; requieren medición real y decisión de privacidad. |

---

## 3. CAMBIOS SOBRE v2 (TABLA DE ENMIENDAS)

| Ref. v2 | Enmienda v3 |
| :-- | :-- |
| §2.2 Alcance (fuera de alcance) | "Modelos de aprendizaje profundo y LLM" **siguen excluidos**. Se permite **un clasificador lineal entrenado offline** (D1). |
| RNF-101 Aislamiento | Se mantiene: **prohibido** contactar el host de la URL analizada (HTTP/TCP/DNS/TLS al objetivo). Se aclara que consultas a **terceros** sobre el *dominio* (PhishTank; RDAP solo si H5-T17 se aprueba) no violan RNF-101 y deben ser opt-in por configuración. |
| RNF-103 Stateless | Se mantiene: cero persistencia de consultas. Se **permiten artefactos de solo lectura** incluidos en la imagen (modelo, allowlist, blocklists). Cero escrituras en disco en runtime. |
| RNF-102 Latencia | Se mantiene `≤ 50 ms` locales **incluyendo** modelo y búsquedas en reputación. |
| RNF-104 Memoria | Se mantiene `≤ 256 MB` **incluyendo artefactos cargados**. |
| RF-302 Niveles | Fronteras del *score* sin cambio: Bajo 0-30, Medio 31-69, Alto 70-100. El score pasa a calcularse con §5. |
| RF-405 PhishTank | Se generaliza a "coincidencia exacta de URL en feed confirmado" (§4, RF-803). |
| §7 Dataset 500/500 (plan pruebas) y 1 000/1 000 (requisitos v2) | **Inconsistentes entre sí**; se reemplazan por el protocolo de §7 de este adendo. |
| Reglas F01-F11 | Se **conservan** (explicabilidad y piso de score). F04 se documenta como regla de baja activación; su ajuste es opcional (H5-T14b) y nunca debe sustituir al modelo. |

---

## 4. REQUISITOS FUNCIONALES NUEVOS

### Módulo 500 — Reputación local (artefactos de solo lectura)

| ID | Requisito |
| :-- | :-- |
| **RF-501** | **PSL vigente.** Reemplazar `publicsuffix2` pinneado por una instantánea vendorizada reciente de la Public Suffix List (secciones ICANN **y** PRIVATE) con versión y fecha registradas. `vercel.app`, `pages.dev`, `netlify.app`, `r2.dev`, `workers.dev`, `github.io`, `web.app`, `replit.app`, `framer.app`, `webflow.io` deben tratarse como sufijos públicos. |
| **RF-502** | **Allowlist.** Artefacto con los dominios registrables del **top-100 000 de Tranco** (ID de lista fijo y registrado). Excluir entradas que sean sufijos públicos según RF-501 y los servicios de RF-503. Coincidencia por dominio registrable del host normalizado. |
| **RF-503** | **Servicios abusables.** Lista (semilla en este adendo, ampliable) de hosts/patrones donde cualquiera publica contenido y que **nunca** se allowlistean: `docs.google.com`, `drive.google.com`, `sites.google.com`, `forms.gle`, `forms.office.com`, `storage.googleapis.com`, `*.s3.amazonaws.com`, `notion.site`, `firebaseapp.com`, `web.app`, `dropbox.com/s/`, acortadores (F05), DDNS conocidos (`duckdns.org`, `no-ip.*`, `ddns.net`). |
| **RF-504** | **Blocklist local.** Artefactos binarios con hashes de 64 bits (`blake2b`, digest 8 bytes, big-endian) **ordenados**, en dos conjuntos: *URL exacta* y *host*. Fuentes gratuitas: Phishing.Database (links y dominios, GitHub), OpenPhish community feed, URLhaus (feed de texto de URLs online) y, si hay app key, el dump de PhishTank. **Verificar disponibilidad y términos de cada feed en H5-T05** y registrar los que no estén disponibles sin bloquear el hito. |
| **RF-505** | **Construcción y refresco en CI.** Un workflow programado (semanal) reconstruye los artefactos, calcula `manifest.json` (fuente, fecha, conteos, SHA-256) y dispara el redeploy. El runtime **no** descarga feeds. |
| **RF-506** | **Carga y consulta.** Carga al arranque en `array('Q')`; consulta por `bisect`. Si un artefacto falta o su SHA-256 no coincide con el manifiesto, el servicio **arranca degradado** (esa fuente se omite, se registra evento `REPUTATION_ARTIFACT_INVALID`) y **nunca** responde 500. |

### Módulo 600 — Clasificador léxico aprendido

| ID | Requisito |
| :-- | :-- |
| **RF-601** | **Featurizador determinista** `extract_features(url) -> dict[int, float]`, función pura, sin red. Hash de características con `zlib.crc32(clave.encode()) % 131072` (**prohibido** `hash()` de Python por aleatorización). Familias (referencia: `accuracy-lab/scripts/feat2.py` con `rules=False`): TLD; n-gramas 2-4 del nombre registrable (`^…$`); tokens de subdominio y de host; tokens de ruta/consulta (≤ 20 caracteres); extensión; numéricas normalizadas (longitud, dígitos, guiones, vocales, racha de consonantes, entropía, nº subdominios, puntos, longitud/profundidad de ruta, https, `@`, puerto, consulta, ruta vacía); **marca en lugar equivocado** (`b_reg`, `b_sub`, `b_path`) con lista de marcas congelada en `app/engine/data/brands.py` generada por script. Debe incluir etiquetas legibles por grupo (§6). |
| **RF-602** | **Modelo.** Artefacto `app/engine/data/model_v1.json` con: `version`, `feature_spec_version`, `n_features`, `bias`, `weights` (índice→peso), `thresholds {medio, alto}`, `trained_at`, `data_manifest` (fuentes, conteos, SHA-256). Inferencia `p = σ(bias + Σ wᵢxᵢ)` en Python puro, sin NumPy/sklearn en producción. |
| **RF-603** | **Calibración de umbrales.** El script de entrenamiento fija `t_medio` = umbral con **FPR ≤ 3 %** y `t_alto` = umbral con **FPR ≤ 1 %** sobre negativos de cola larga **retenidos** (agrupados por dominio). Ambos pueden sobrescribirse por entorno (`MODEL_THRESHOLD_MEDIO`, `MODEL_THRESHOLD_ALTO`) sin recompilar. |
| **RF-604** | **Explicabilidad.** Contribución por característica `wᵢxᵢ` agrupada por prefijo (§6). El modelo expone `explain(url) -> dict[grupo, contribución_positiva]`. |
| **RF-605** | **Pipeline de entrenamiento reproducible** (`scripts/ml/`): `fetch_data.py`, `build_dataset.py`, `train.py`, `evaluate.py`, `export_model.py`. Semillas fijas, cap de 3 URLs por dominio registrable, negativos por bandas de ranking (1k/10k/100k/1M) con rutas legítimas reales (50 %), negativos difíciles obligatorios, hash de datos en el manifiesto. Dependencias de entrenamiento solo en `requirements-ml.txt` (**no** en `requirements.txt`). |
| **RF-606** | **Negativos difíciles.** Mantener `tests/data/hard_negatives.txt` con **≥ 200** URLs legítimas de login/seguridad/soporte de sitios reales (semilla: 48 en `accuracy-lab/data/`), más generación sintética `top-1000 dominios × plantillas` (`/login`, `/signin`, `/account/verify`, `/security`, `/oauth2/authorize?…`). Con el sistema completo, **0 deben salir Medio/Alto**. |

### Módulo 700 — Scoring v3 (normativo en §5)

| ID | Requisito |
| :-- | :-- |
| **RF-701** | `S_rules` = score v2 (`min(100, Σ wᵢ·fᵢ)`), sin cambios. |
| **RF-702** | `S_ml = PL(p)` lineal por tramos con nudos `(0,0)`, `(t_medio,31)`, `(t_alto,70)`, `(1,100)`, redondeado a entero. |
| **RF-703** | `S_pre = max(S_rules, S_ml)`. |
| **RF-704** | **Evidencias ML aditivas:** si `S_ml > S_rules`, `Δ = S_ml − S_rules` se reparte (método del mayor resto) entre los grupos con contribución positiva; se muestran los 3 mayores con ≥ 1 punto. Si no, no hay evidencias ML. La suma de `points` de las evidencias debe igualar el score antes de reputación. |
| **RF-705** | **Allowlist:** si el dominio registrable ∈ allowlist (RF-502), no está en RF-503 y no hay coincidencia exacta confirmada: `score = min(score, 30)` y se agrega la evidencia informativa `TRUSTED_DOMAIN` con `points = 0`. |
| **RF-706** | Los **piso de nivel** y bonificaciones de feeds se aplican según §5, paso 4. |

### Módulo 800 — Reputación externa (extiende RF-4xx)

| ID | Requisito |
| :-- | :-- |
| **RF-801** | **PhishTank con variantes.** Consultar, en orden y hasta agotar el timeout global de 4.0 s: URL original saneada, URL normalizada, y variante con/sin barra final. Soportar `PHISHTANK_APP_KEY` **opcional** vía `BaseSettings` (nunca en duro). Registrar el estado por variante sin la URL. |
| **RF-802** | La caché LRU/TTL existente se extiende para cubrir las variantes (clave = SHA-256 de la variante). |
| **RF-803** | **Coincidencia exacta de URL** en feed local confirmado (RF-504) o PhishTank válido: `+50`, nivel **Alto** (generaliza RF-405), evidencia `MATCH_FEED_URL` (o `MATCH_PHISHTANK`, sin cambios, para PhishTank). Gana sobre la allowlist. |
| **RF-804** | **Coincidencia por host** en feed local, dominio no allowlisteado ni abusable: `+40`, **piso de nivel Medio**, evidencia `MATCH_FEED_HOST`. Si el dominio está en la allowlist, se ignora. |
| **RF-805** | `phishtank_status` conserva su enum; los feeds locales no lo alteran. |

### Módulo 900 — Enriquecimiento opcional (condicional)

| ID | Requisito |
| :-- | :-- |
| **RF-901** | **Edad de dominio vía RDAP** (consulta a terceros, solo el *dominio*, nunca la URL completa). Desactivado por defecto (`ENABLE_RDAP=false`). Solo se promueve a activado si H5-T17 demuestra con datos reales mejora de recall ≥ 3 puntos a FPR constante y p95 de latencia total ≤ 1.5 s con degradación elegante. Evidencia `NEW_DOMAIN` (+15 si < 30 días). |

---

## 5. ALGORITMO DE SCORING v3 (NORMATIVO)

```text
ENTRADA: parsed, S_rules (v2), p (modelo), A (allowlist), B (abusable),
         FU (feed URL exacta confirmada o PhishTank valid), PU (PhishTank unverified),
         FH (feed por host)

1. S_ml  = PL(p)                      # nudos (0,0) (t_medio,31) (t_alto,70) (1,100)
2. S     = max(S_rules, S_ml)
3. Si A y no B y no FU:  S = min(S, 30)  ; añadir TRUSTED_DOMAIN(points=0)
4. Reputación:
     si FU:            S = min(100, S + 50)  ; nivel = Alto          (RF-803)
     si PU y no FU:    S = min(100, S + 15)                          (v2, Opción B)
     si FH y no A y no B y no FU:  S = min(100, S + 40) ; nivel >= Medio   (RF-804)
5. nivel = clasificar(S) salvo forzados del paso 4 (el mayor entre ambos)
6. Evidencias = reglas v2 activas + evidencias ML (RF-704) + evidencias de reputación
```

**Reglas de precedencia:** FU > A > FH > modelo/reglas. Un fallo de cualquier componente (modelo, artefacto, PhishTank) degrada a la combinación restante y **nunca** produce HTTP 500.

---

## 6. CONTRATO DE API Y CATÁLOGO DE EVIDENCIAS

El JSON de respuesta **no cambia**. Solo se agregan estos `rule_id` (textos es-419 a cargo de `app/scoring/evidence.py`):

| rule_id | Origen | Título (resumen) |
| :-- | :-- | :-- |
| `ML_TLD_RISK` | prefijo `tld=` | Extensión de dominio frecuente en phishing |
| `ML_DOMAIN_SHAPE` | `r2:/r3:/r4:` y numéricas del dominio | Nombre de dominio aleatorio o atípico |
| `ML_HOST_PATTERN` | `st:`, `ht:`, nº subdominios | Patrones sospechosos en el nombre del host |
| `ML_PATH_PATTERN` | `pt:`, `ext=`, longitud/profundidad de ruta | Ruta con patrones típicos de phishing |
| `ML_BRAND_MISMATCH` | `b_reg`, `b_sub`, `b_path` | Marca conocida en un dominio que no es el oficial |
| `ML_URL_SHAPE` | resto (https, `@`, puerto, longitud total) | Estructura general inusual |
| `MATCH_FEED_URL` | RF-803 | URL reportada en una lista de phishing |
| `MATCH_FEED_HOST` | RF-804 | Dominio reportado en una lista de phishing |
| `TRUSTED_DOMAIN` | RF-705 | Dominio de alta reputación (informativa, 0 puntos) |
| `NEW_DOMAIN` | RF-901 (condicional) | Dominio registrado recientemente |

---

## 7. PROTOCOLO DE EVALUACIÓN Y KPIs (REEMPLAZA §7 DEL PLAN DE PRUEBAS)

**Particiones obligatorias** (informar cada una por separado):
1. **Agrupada por dominio registrable** (70/30).
2. **Cruzada entre fuentes** (PhishDB→JPCERT y JPCERT→PhishDB).
3. **Temporal** (JPCERT ≤ 2023 → 2025-2026).
4. **Negativos difíciles** (RF-606), contados aparte.

**Métricas:** AUC, PR-AUC, Recall@FPR (0.3 %, 1 %, 3 %, 5 %), matriz de confusión con **positivo = Medio+Alto** (como §6.2 del plan de pruebas), desglose por fuente, latencia p50/p95, RAM pico.

**Metas de aceptación (sistema completo, medidas en `scripts/ml/evaluate.py` y en la API local):**

| KPI | Meta | Referencia prototipo |
| :-- | :-- | :-- |
| Recall (Medio+Alto), agrupada por dominio, FPR ≤ 3 % | **≥ 92 %** | 94.5 % |
| Recall, temporal 2025-26, FPR ≤ 3 % | **≥ 88 %** | 92 % |
| Recall, cruzada entre fuentes, FPR ≤ 3 % | **≥ 78 %** | 80-86 % |
| Negativos difíciles marcados Medio/Alto | **0 / ≥ 200** | 0 / 48 con allowlist |
| Recall del motor v2 (para comparar) | informativo | 1.9 % |
| Latencia local | ≤ 50 ms (p95) | 0.19 ms modelo |
| RAM del contenedor con artefactos | ≤ 256 MB | blocklist 9.4 MB |
| Contrato `/api/v1/analyze` | idéntico | — |

> Las metas se ajustan **solo** con evidencia, nunca bajando el umbral para "ganar" un KPI sin informarlo. Si la meta temporal o cruzada no se alcanza, el informe lo declara.

**Benchmark contra la API desplegada:** `RATE_LIMIT_PER_MINUTE=30` hace inviable enviar miles de URLs a Render (≈ 3 h por 5 000). La evaluación masiva se ejecuta **en proceso/local** (`RATE_LIMIT_PER_MINUTE` alto en entorno de prueba); contra Render se corre una muestra de humo (≤ 300 URLs) respetando el límite.

---

## 8. REQUISITOS NO FUNCIONALES NUEVOS

| ID | Requisito |
| :-- | :-- |
| **RNF-107** | **Integridad de artefactos:** `manifest.json` con SHA-256 verificado al arranque; tamaño máximo por artefacto y por imagen (imagen final < 220 MB). |
| **RNF-108** | **Reproducibilidad:** mismo manifiesto de datos + semilla → mismo modelo y mismas métricas (±0.001 AUC). |
| **RNF-109** | **Arranque en frío:** carga de modelo y artefactos en ≤ 3 s en el plan gratuito; no bloquear `/health`. |
| **RNF-110** | **Seguridad:** el featurizador y los parsers de feeds no usan regex con backtracking catastrófico, `eval`/`exec`, ni `pickle`; los artefactos son JSON o binarios planos. |
| **RNF-111** | **Privacidad:** nunca registrar URL ni dominio en claro (se mantiene el hash SHA-256 de v2). |

---

## 9. CASOS DE PRUEBA NUEVOS

| ID | Escenario | Resultado esperado |
| :-- | :-- | :-- |
| `TC-RF-501-01` | `a.vercel.app` y `b.vercel.app` | Dominios registrables distintos; ninguno allowlisteado. |
| `TC-RF-502-01` | `https://www.paypal.com/signin` | `TRUSTED_DOMAIN`, score ≤ 30, Bajo. |
| `TC-RF-502-02` | `https://paypal.com.evil.cn/signin` | Dominio registrable `evil.cn`; sin allowlist; Medio/Alto. |
| `TC-RF-503-01` | `https://docs.google.com/forms/d/e/…/viewform` | **No** allowlisteada; decide el modelo. |
| `TC-RF-504-01` | Hash de URL presente en blocklist de prueba | `MATCH_FEED_URL`, +50, Alto. |
| `TC-RF-506-01` | Artefacto con SHA-256 alterado | Arranque degradado, HTTP 200, evento de registro. |
| `TC-RF-601-01` | 20 URLs con vectores esperados congelados | Paridad exacta de índices y valores. |
| `TC-RF-602-01` | 500 URLs: inferencia pura vs. referencia sklearn | Diferencia máx. < 1e-3. |
| `TC-RF-704-01` | `S_ml=60`, `S_rules=15` | Evidencias ML suman 45 puntos; total = 60. |
| `TC-RF-705-01` | Dominio allowlisteado con F11+F08+F01 (=45 en v2) | Score ≤ 30, Bajo. |
| `TC-RF-801-01` | URL en PhishTank solo con barra final | Match por variante (con `respx`). |
| `TC-RF-804-01` | Host en feed, dominio allowlisteado | Sin puntos de feed (se ignora). |
| `TC-EVAL-01` | Set difícil ≥ 200 | 0 Medio/Alto. |
| `TC-EVAL-02` | Mini-benchmark congelado (400 URLs) | Recall y FPR no empeoran > 1 punto vs. línea base del hito (regresión en CI). |
| `TC-RNF-102-v3` | Pipeline completo (modelo+reputación) | p95 ≤ 50 ms. |
| `TC-RNF-104-v3` | Contenedor con artefactos cargados | RAM ≤ 256 MB. |

Los tests existentes con dominios de ejemplo (`example.com`, etc.) deben **inyectar una allowlist vacía** o usar dominios fuera del top-100k para no depender del ranking.

---

## 10. LIMITACIONES Y RIESGOS (HONESTIDAD CIENTÍFICA)

| Riesgo | Impacto | Mitigación |
| :-- | :-- | :-- |
| Negativos de entrenamiento sesgados a sitios populares | FPR real mayor en sitios pequeños | Informar el sesgo; añadir negativos de cola larga; calibrar `t_medio` con FPR ≤ 3 %; umbrales configurables. |
| Dominios aleatorios cortos sin otras señales (`vgydea.com`) | Residuo de FN léxicos | RF-901 condicional; feeds para phishing fresco. |
| Deriva temporal de campañas | Pérdida de recall con el tiempo | Reentrenamiento programado; prueba temporal en CI de evaluación. |
| Phishing alojado en dominios reputados comprometidos | Allowlist lo deja pasar (≤ 0.9 % medido) | RF-803 prevalece sobre la allowlist; RF-503. |
| Feeds con falsos positivos | Alarmas injustificadas | RF-804 ignora hosts allowlisteados; el nivel mínimo es Medio. |
| Adversario conoce el modelo | Evasión | Reentrenar; reglas v2 como piso; el resultado es "evaluación preliminar", no veredicto. |
| **Alineación con el anteproyecto** | El anteproyecto declara "no entrenar modelos complejos" y un enfoque de reglas interpretables | Un modelo **lineal e interpretable** con evidencias aditivas es compatible con la fase "Validación, ajustes y análisis de resultados"; documentarlo como iteración basada en evidencia y **consultar al docente** si el proyecto aún está en evaluación. |

---

**Pendiente de aprobación para implementación bajo SDD (Hito 5).**
