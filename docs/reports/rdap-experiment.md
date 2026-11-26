# Experimento RDAP — edad de dominio (H5-T17 / RF-901)

Generado: `2026-11-26T12:59:47.727967+00:00` · modo: `live` · semilla: 5.

## Protocolo

- Muestra retenida del benchmark congelado (`data/processed/benchmark.tsv`), una URL por dominio registrable, equilibrada entre positivos y negativos.
- El sistema v3 se evalúa en proceso con PhishTank deshabilitado y sin tráfico hacia el host analizado (RNF-101). Umbrales y allowlist intactos.
- Solo se consulta el dominio registrable a servidores RDAP públicos obtenidos del bootstrap de IANA. Pausa configurable entre consultas, 3 reintentos ante fallo y caché en disco.
- La señal `NEW_DOMAIN` suma +15 si la fecha de registro tiene menos de 30 días; los dominios allowlisted no abusables siguen topados en 30.
- `Recall@FPR` barre umbrales y toma el máximo recall con FPR ≤ objetivo, igual que el protocolo del adendo §7. Objetivo primario: FPR ≤ 3 %.

## Muestra y cobertura

| Métrica | Valor |
| :-- | --: |
| Dominios únicos consultados | 1599 |
| Positivos / negativos | 799 / 800 |
| Respuestas con fecha de registro | 804 |
| Dominios nuevos (< 30 días) | 5 |
| Nuevos positivos / negativos | 4 / 1 |
| Sin servidor / no registrados / errores / no consultados (offline) | 336 / 379 / 80 / 0 |

## Resultado

| FPR objetivo | Recall v3 | Recall + RDAP | Δ (pp) | Umbral v3 → +RDAP |
| --: | --: | --: | --: | --: |
| ≤ 1% | 0.959 | 0.959 | +0.00 | 31 → 31 |
| ≤ 3% | 0.959 | 0.959 | +0.00 | 31 → 31 |

## Interpretación

Solo 4 de 799 positivos (0.5%) tenían menos de 30 días al consultarlos. El corpus congelado está formado por campañas ya reportadas, por lo que la edad no discrimina entre clase positiva y negativa: la señal no puede elevar el recall sin elevar también los falsos positivos. **No se bajaron umbrales ni se relajó la allowlist para forzar la mejora.** Una futura evaluación con feeds de phishing fresco y dominios aleatorios cortos de registro reciente debe repetir este protocolo antes de reabrir H5-T17; la forma del nombre, por sí sola, no basta (ver caso ilustrativo).

## Caso ilustrativo

`vgydea.com`: registrado hace **1440 días**. `NEW_DOMAIN` no dispara: la heurística de dominio aleatorio corto no se beneficia de RDAP en este ejemplo cuando el registro es antiguo.

## Latencia

| Métrica | ms |
| :-- | --: |
| p95 análisis v3 local | 3.46 |
| p95 consulta RDAP | 266.28 |
| p95 total (v3 + RDAP) | 269.12 |

## Decisión

**NO cumple el criterio de promoción**: no se implementa el cliente RDAP en producción; la señal queda documentada como experimento negativo.

- Criterio: mejora ≥ 3 puntos de recall a FPR ≤ 3 % y p95 total ≤ 1 500 ms.
- Si no se cumple, **no se implementa** el cliente RDAP en `app/`; el experimento queda como evidencia y `ENABLE_RDAP` no se añade.

## Limitaciones y privacidad

- Los positivos del benchmark ya fueron reportados y muchos dominios fueron dados de baja: la fecha de registro no siempre describe phishing fresco.
- Un 404 se trata como «no registrado»/indisponible, nunca como dominio nuevo.
- Solo sale el dominio registrable hacia el servidor RDAP de su TLD; nunca la URL, el path ni datos del usuario. El tráfico real requiere `LINKGUARD_RDAP_LIVE=1` y `--live`: **CI no realiza consultas**.
- El modo `--offline` reproduce el informe desde la caché; las fechas se miden relativas al día de la consulta, por lo que el resultado es estable mientras la caché no se refresque. Las entradas servidas desde caché registran 0 ms: una regeneración offline da una cota inferior de la latencia. En la pasada `live` se mide solo la latencia HTTP; no se incluyen las pausas entre consultas ni el costo de programar al productor.
