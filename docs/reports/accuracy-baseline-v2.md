# Línea base del motor v2 — H5-T02

**Fecha:** 2026-11-25T23:36:28.977526+00:00
**Dataset:** `data/processed/benchmark.tsv` (SHA-256 `9b55df5c0436d9db5be674038217631342250282b64dcb54632314f98c0a6e66`)
**Filas:** 7812 · **Errores de normalización:** 0
**Motor:** v2 (`normalize -> run_rules -> score_results`), en proceso, sin PhishTank ni HTTP.

## 1. Resumen global

| Métrica | Valor |
| :-- | --: |
| TP (Medio+Alto en positivos) | 85 |
| FN (Bajo en positivos) | 4679 |
| FP (Medio+Alto en negativos) | 2 |
| TN (Bajo en negativos) | 3046 |
| Precisión | 0.977 |
| Recall | 0.018 (1.8 %) |
| F1 | 0.035 |
| Exactitud | 0.401 |
| FPR | 0.001 (0.1 %) |

### Comparación con el laboratorio

| Métrica | `RESULTS.md` | Medición | Δ |
| :-- | --: | --: | --: |
| Recall | 0.019 | 0.018 | -0.1 pp |
| F1 | 0.037 | 0.035 | -0.002 |
| JPCERT Bajo | 98.4 % | 98.4 % | -0.0 pp |

La medición **reproduce la línea base dentro de ±1 punto**: recall, F1 y proporción de Bajo en JPCERT coinciden con `RESULTS.md`.

## 2. Matriz de confusión por fuente

| Fuente | n | Bajo | Medio | Alto | % Bajo | % Medio+Alto |
| :-- | --: | --: | --: | --: | --: | --: |
| citizenlab | 1500 | 1500 | 0 | 0 | 100.0 % | 0.0 % |
| hardneg | 48 | 46 | 2 | 0 | 95.8 % | 4.2 % |
| jpcert | 2364 | 2326 | 38 | 0 | 98.4 % | 1.6 % |
| phishdb | 2400 | 2353 | 46 | 1 | 98.0 % | 2.0 % |
| top10k | 1500 | 1500 | 0 | 0 | 100.0 % | 0.0 % |

## 3. Recall@FPR (barrido del score)

El motor v2 no expone probabilidades; se barre el umbral de score para trazar la curva y se reporta el máximo recall con FPR <= objetivo.

| FPR objetivo | Recall máximo | Umbral de score |
| --: | --: | --: |
| 0.3 % | 2.0 % | 30 |
| 1.0 % | 10.2 % | 17 |
| 3.0 % | 20.4 % | 15 |
| 5.0 % | 35.1 % | 7 |

## 4. Particiones

### 4.1 Agrupada por dominio registrable (70/30)

| Métrica | Valor |
| :-- | --: |
| n (30 % de dominios en reserva) | 2358 |
| Positivos | 1437 |
| Negativos | 921 |
| Recall | 0.018 (1.8 %) |
| FPR | 0.002 (0.2 %) |
| F1 | 0.035 |

### 4.2 Cruzada entre fuentes

| Fuente positiva | n | Recall | % Bajo |
| :-- | --: | --: | --: |
| jpcert | 2364 | 1.6 % | 98.4 % |
| phishdb | 2400 | 2.0 % | 98.0 % |

### 4.3 Temporal (JPCERT)

| Partición | Positivos | Recall |
| :-- | --: | --: |
| JPCERT <= 2023 | 1484 | 2.4 % |
| JPCERT 2025-2026 | 587 | 0.3 % |

## 5. Desglose por año (JPCERT)

| Año | Positivos | Bajo | Medio | Alto | Recall |
| :-- | --: | --: | --: | --: | --: |
| 2019 | 289 | 283 | 6 | 0 | 2.1 % |
| 2020 | 299 | 272 | 27 | 0 | 9.0 % |
| 2021 | 300 | 298 | 2 | 0 | 0.7 % |
| 2022 | 298 | 297 | 1 | 0 | 0.3 % |
| 2023 | 298 | 298 | 0 | 0 | 0.0 % |
| 2024 | 293 | 293 | 0 | 0 | 0.0 % |
| 2025 | 296 | 296 | 0 | 0 | 0.0 % |
| 2026 | 291 | 289 | 2 | 0 | 0.7 % |

## 6. Latencia local

| Métrica | ms/URL |
| :-- | --: |
| p50 | 0.114 |
| p95 | 0.186 |
| Media | 0.127 |

## 7. Reglas más activadas

| Regla | Activaciones | % de URLs |
| :-- | --: | --: |
| F11_SOCIAL_ENGINEERING_KEYWORDS | 910 | 11.6 % |
| F01_EXCESSIVE_LENGTH | 627 | 8.0 % |
| F07_HYPHENS_IN_DOMAIN | 324 | 4.1 % |
| F03_MULTIPLE_SUBDOMAINS | 306 | 3.9 % |
| F02_DIRECT_IP | 60 | 0.8 % |
| F05_URL_SHORTENER | 37 | 0.5 % |
| F08_SCHEMA_REDIRECT | 26 | 0.3 % |
| F06_AT_SYMBOL | 13 | 0.2 % |
| F04_SHANNON_ENTROPY | 7 | 0.1 % |
| F10_SPECIAL_CHARS_RATIO | 4 | 0.1 % |
| F09_NON_STANDARD_PORT | 4 | 0.1 % |

## 8. Limitaciones

- Negativos tomados de rankings populares: el FPR sobre sitios legítimos pequeños (fuera del top-1M) no se mide.
- Positivos de JPCERT y Phishing.Database ya dados de baja o agregados: no equivalen a phishing recién creado.
- La edad de dominio, DNS y certificados no se miden en este laboratorio (candidatos a `RF-901`, condicional).
- El motor v2 tiene un techo estructural de recall: suma de señales débiles y umbral Alto de 70 puntos. Este informe es la línea base que el modelo lineal de `H5-T09` debe superar.

