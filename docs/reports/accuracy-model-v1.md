# Modelo léxico v1 — Precisión y robustez (H5-T09)

> Artefacto: `app/engine/data/model_v1.json` · Especificación: RF-602/RF-603/RF-605/RF-606.
> Protocolo: adendo v3 §7. Semilla fija `5`, sin red, sin `pickle` (RNF-108/RNF-110).

## Configuración

| Parámetro | Valor |
| :-- | --: |
| Regresión | Logística, `class_weight=balanced`, `C=3`, `liblinear` |
| Espacio de características | 131 072 cubos (`zlib.crc32 % 2^17`) |
| Filas del dataset | 77 642 (dataset T02; 70 % entrenamiento, 30 % retenido) |
| Semilla | 5 |
| `t_medio` (FPR ≤ 3 %) | 0.537848 |
| `t_alto` (FPR ≤ 1 %) | 0.854156 |
| SHA-256 del dataset | `1269343745a539350b6adcf0e5307229032fe42f6de6c557b3c344bc7cf7a38a` |

## Particiones obligatorias

| Partición | n | AUC | PR-AUC | R@0.3 % | R@1 % | R@3 % | R@5 % |
| :-- | --: | --: | --: | --: | --: | --: | --: |
| agrupada | 23,380 | 0.9895 | 0.9907 | 75.6% | 88.1% | 93.4% | 95.4% |
| cruzada_phishdb_a_jpcert | 17,432 | 0.9718 | 0.9590 | 59.6% | 75.8% | 84.5% | 88.0% |
| cruzada_jpcert_a_phishdb | 17,270 | 0.9591 | 0.9367 | 44.9% | 60.5% | 76.2% | 82.5% |
| temporal | 12,643 | 0.9826 | 0.9244 | 67.1% | 81.5% | 90.0% | 93.3% |

### Matriz de confusión (agrupada, positivo = Medio+Alto, umbral `t_medio`)

| TP | FP | FN | TN |
| --: | --: | --: | --: |
| 11264 | 339 | 794 | 10983 |

## Negativos difíciles (RF-606)

- URLs evaluadas: **3048** (48 reales + top-1000 Tranco × plantillas).
- Marcadas por encima de `t_medio`: **2691**.
- Marcadas por encima de `t_alto`: **2137**.
- El criterio normativo `0 Medio/Alto` se verifica con el sistema completo (modelo + allowlist + feeds) en H5-T14; aquí se mide solo el modelo, sin allowlist.

## Artefacto, poda y paridad

| Métrica | Valor |
| :-- | --: |
| Tamaño | 2,693,349 bytes (2.569 MB) |
| Pesos no nulos originales | 116,836 |
| Pesos retenidos (`|w| ≥ 0.002`) | 93,904 |
| Pesos podados | 22,932 |
| AUC antes de podar | 0.9901 |
| AUC después de podar | 0.9901 |
| Δ AUC por poda | +0.00000 |
| Error máx. inferencia pura vs sklearn (500 URL) | 6.66e-16 |
| SHA-256 del modelo | `2330d0659d4e8c81565c99854af6dbeb572e99c10ddbb2ee3853e510ac905dcb` |

## Metas de referencia (no se bajan en silencio)

| Meta | Objetivo | Medición | Resultado |
| :-- | --: | --: | :-- |
| Agrupada @FPR 3 % | ≥ 94% | 93.4% | ⚠️ (causa abajo) |
| Cruzada PhishDB→JPCERT @FPR 3 % | ≥ 78% | 84.5% | ✅ |
| Cruzada JPCERT→PhishDB @FPR 3 % | ≥ 78% | 76.2% | ⚠️ (causa abajo) |
| Temporal 2025-26 @FPR 3 % | ≥ 88% | 90.0% | ✅ |

## Causa de las desviaciones

- **Agrupada 93.4 % vs. 94 % de referencia (0.6 pp):** la referencia se midió con `publicsuffix2` y un corpus de laboratorio más pequeño. Tras H5-T04 la segmentación de `reg`/`sub` usa la PSL vendorizada, lo que cambia los n-gramas y los tokens de host; el dataset T02 además incluye fuentes actualizadas a 2026. El valor sigue por encima de la meta normativa del adendo §7 (≥ 92 % @FPR 3 %). No se ajustaron umbrales para inflar el KPI.
- **Cruzada JPCERT→PhishDB 76.2 % vs. 78 % de referencia (1.8 pp):** el cambio de fuente implica un cambio de distribución (JPCERT es mayoritariamente japonés; Phishing.Database es global y tiene más dominios cortos aleatorios). El AUC de 0.9591 en esta partición confirma la brecha de dominio; se reporta sin recalibrar umbrales sobre el conjunto de prueba.

## Notas y limitaciones

- Las metas del adendo §7 fijan agrupada ≥ 92 %, temporal ≥ 88 % y cruzada ≥ 78 %; la tabla anterior usa además la referencia de 94 % agrupada del laboratorio.
- La calibración usa negativos retenidos por dominio para evitar fuga de dominios entre entrenamiento y umbrales (RF-603).
- Los positivos son URLs ya reportadas/dadas de baja; no representan phishing recién creado.
- Los negativos provienen de rankings populares: el FPR en sitios pequeños fuera del top-1M no está medido.
- La edad del dominio, DNS y certificados quedan fuera del modelo (H5-T17 es condicional).
- El featurizador usa la PSL vendorizada de H5-T04; los vectores del laboratorio hechos con `publicsuffix2` no son comparables byte a byte.
