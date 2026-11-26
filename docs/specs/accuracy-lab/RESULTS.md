# Resultados medidos (prototipo), 24-nov-2026

## A. Línea base del motor v2 (solo reglas léxicas, sin PhishTank)
| Fuente | n | Bajo | Medio | Alto |
| :-- | --: | --: | --: | --: |
| JPCERT (estratificado 2019-2026) | 2400 | 98.4 % | 1.5 % | 0.1 % |
| Phishing.Database (global) | 2400 | 97.8 % | 2.0 % | 0.2 % |
| Negativos top-10k | 1500 | 100 % | 0 | 0 |
| Negativos Citizen Lab (rutas reales) | 1500 | 99.9 % | 0.1 % | 0 |
| Negativos difíciles (login de sitios reales) | 48 | 95.8 % | 4.2 % | 0 |

TP=90, FN=4710, FP=3, TN=3045: **Accuracy 0.399, Precision 0.968, Recall 0.019, F1 0.037**.
69.7 % de JPCERT obtiene score 0. F04 y F09 no se activaron ni una vez; F06 < 0.1 %.

## B. Clasificador lineal (regresión logística, hashing 2^17, Python puro)
| Prueba | AUC | Recall @FPR 0.5 % | @1 % | @3 % |
| :-- | --: | --: | --: | --: |
| A. Agrupada por dominio | 0.991 | 86 % | 90 % | 94.5 % |
| B. Entrenar PhishDB, probar JPCERT | 0.973 | 71 % | 79 % | 86 % |
| C. Entrenar JPCERT, probar PhishDB | 0.961 | 60 % | 69 % | 80 % |
| D. Temporal JPCERT 2019-23 a 2025-26 | 0.987 | 79 % (@0.3 %) | 86 % | 92 % |

* Inferencia 0.19 ms/URL; diferencia máx. vs sklearn 9e-5; JSON 1.7 MB.
* Marca-en-lugar-equivocado y flags F01-F11: +0.4 a +1 punto.
* **Sin allowlist se marcan 36/48 (FPR 1 %) o 42/48 (FPR 3 %) logins legítimos difíciles.**
* Allowlist por ranking, difíciles aún marcados: top-1k 8/48, top-10k 3/48, **top-100k 0/48**. Costo: positivos en top-100k = 0.40 % (JPCERT) / 0.89 % (PhishDB).

## C. Feeds y estructuras
* Hosts de JPCERT presentes hoy en Phishing.Database ACTIVE: 0.1 % a 6.1 % según año.
* Ese feed contiene dominios legítimos de alto ranking (mercadolibre.com.ar, pastebin.com, getpocket.com): un match por host no puede anular la allowlist.
* 1.18 M hashes: `set[int]` ≈ 34 MB (≈70 MB con los enteros) vs `array('Q')` ordenado **9.4 MB**, búsqueda binaria 0.9 µs.
* `publicsuffix2==2.20191221` trata vercel.app, pages.dev, netlify.app, r2.dev, replit.app, framer.app y webflow.io como un único dominio registrable.

## D. Límites de la medición
1. Negativos tomados de rankings populares: FPR sobre sitios legítimos pequeños (fuera del top-1M) no medido.
2. Positivos ya dados de baja (JPCERT) o agregados: no equivalen a phishing recién creado.
3. Edad de dominio, DNS y certificados (señales para dominios aleatorios cortos como `vgydea.com`) no medibles en el laboratorio.
