# accuracy-lab — Implementación de REFERENCIA (prototipo medido)

> **No es código de producción.** Es el prototipo con el que se midió la línea base y la mejora potencial
> de LinkGuard (ver `RESULTS.md`). Los agentes de OpenCode deben **portar** estas ideas a `linkguard-backend`
> respetando `AGENTS.md`, type hints, docstrings es-419, tests y las specs `docs/specs/`.
> Los scripts tienen rutas absolutas del entorno de laboratorio (`/home/claude/...`): parametrizarlas al portar.

| Archivo | Qué hace |
| :-- | :-- |
| `scripts/sample.py`, `base.py` | Muestreo estratificado de JPCERT y línea base del motor v2 (solo léxico). |
| `scripts/build.py`, `eval_base.py` | Benchmark etiquetado y matriz de confusión del motor v2. |
| `scripts/mk.py` | Dataset de entrenamiento (cap de 3 URLs por dominio registrable; negativos por bandas de ranking; rutas legítimas reales). |
| `scripts/feat.py`, `feat2.py` | **Featurizador de referencia** (hashing `zlib.crc32` mod 2^17; n-gramas del dominio, TLD, tokens, rutas, numéricas, marca-en-lugar-equivocado). |
| `scripts/train.py`, `train2.py` | Regresión logística; particiones agrupada por dominio y cruzada entre fuentes. |
| `scripts/temporal.py` | Partición temporal (entrenar ≤2023, probar 2025-26). |
| `scripts/export.py` | Exporta pesos a JSON, verifica paridad en Python puro, latencia y umbrales por FPR. |
| `scripts/allow.py` | Costo/beneficio de la allowlist por banda de ranking. |
| `scripts/err.py` | Análisis de errores (FN/FP). |
| `data/model_proto.json` | Modelo prototipo (1.7 MB). Solo demostrativo: reentrenar con el pipeline oficial. |
| `data/hard_negatives_seed.txt` | 48 URLs legítimas "difíciles" (login/seguridad de sitios reales): semilla del set de ≥200. |

Dependencias solo de laboratorio: `scikit-learn`, `numpy`, `scipy`, `publicsuffix2`. La inferencia en producción es Python puro.
Fuentes (gratuitas): JPCERT phishurl-list · mitchellkrogza/Phishing.Database · zer0h/top-1000000-domains (sustituir por **Tranco** con ID fijo) · citizenlab/test-lists.
