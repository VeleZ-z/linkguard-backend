# Verificación de la hipótesis C6 — variantes de PhishTank (H5-T13)

> Spec: `docs/specs/linkguard-especificacion-accuracy-v3.md` §1 (C6), §8 (RF-801/RF-802)
> Código: `app/clients/phishtank.py`, `scripts/verify_phishtank_live.py`

## 1. Hipótesis

C6 plantea que el cliente consultaba la URL **ya normalizada** (con `http://`
inyectado, `%XX` decodificado y host convertido a punycode) mientras PhishTank
empareja la URL **exacta** reportada. Sin `app_key`, además, un benchmark masivo
podría caer en límite de tasa.

## 2. Resultado de la revisión de código (previo a T13)

**C6 CONFIRMADA por revisión estática.** El cliente anterior ejecutaba una sola
petición:

```python
await client.post(API_URL, data={"url": url, "format": "json"})
```

y `app/services/analyzer.py` le pasaba `parsed.normalized_url`. Por tanto, una
URL reportada como `example.com/ruta%20x` se consultaba como
`http://example.com/ruta x`; un reporte almacenado sin esquema o con barra final
distinta tampoco podía coincidir. No existía `app_key` ni compensación por
variantes.

## 3. Mitigación implantada (RF-801/RF-802)

1. `PhishtankClient.build_variants()` genera, en orden, la URL original saneada,
   la normalizada por el motor local, la variante sin barra final y la variante
   con barra final (`MAX_VARIANTS = 4`). Se descartan duplicados antes de consultar.
2. `check_url()` prueba las variantes con un **presupuesto global** de
   `PHISHTANK_TIMEOUT` (4.0 s por defecto): el `remaining` se recalcula antes de
   cada petición, de modo que cuatro variantes no pueden sumar 16 s.
3. La caché LRU/TTL existente se reutiliza con clave `SHA-256` de cada variante.
   Un negativo —de red o cacheado— no detiene la búsqueda de las variantes
   restantes; un reporte confirmado o pendiente de verificación devuelve
   `status="cached"`/`"available"` de inmediato. Así `TC-RF-801-01` encuentra
   el match de la barra final en una sola invocación.
4. `PHISHTANK_APP_KEY` es opcional y se lee por `BaseSettings`; se envía como
   campo `app_key` del cuerpo y nunca se escribe en logs ni en el contrato.
5. Los 4xx/5xx detienen el intento de variantes (evitan agravar un 429); los
   timeouts agotan el plazo restante y degradan a `status="timeout"`.
6. Cada variante registra `PHISHTANK_VARIANT label=… status=… sha256=…` sin URL
   ni dominio en claro.

## 4. Verificación empírica (script opt-in)

`scripts/verify_phishtank_live.py` descarga una muestra de 20 URLs del feed
público de PhishTank, consulta las cuatro variantes y reporta:

* tasa de acierto por variante;
* variante que produce el primer acierto;
* respuestas 429 y errores por tipo;
* dictamen automático de C6 comparando `original_saneada` contra `normalizada`.

**Estado en esta sesión: NO EJECUTADO.** El script exige
`LINKGUARD_LIVE_TESTS=1` y la suite de CI tiene prohibido el tráfico real; no se
autorizó salida a `data.phishtank.com` ni se dispuso de una clave real. Ejecución
en modo seguro (sin la variable):

```json
{"estado": "OMITIDO", "motivo": "LINKGUARD_LIVE_TESTS != 1 (el CI nunca hace tráfico real)"}
```

Para completar la verificación en un entorno autorizado:

```bash
LINKGUARD_LIVE_TESTS=1 .venv/bin/python scripts/verify_phishtank_live.py \
  > docs/reports/phishtank-live-c6.json
```

La salida no contiene URLs ni credenciales. Si `normalizada` obtiene menor tasa
que `original_saneada`, C6 queda confirmada empíricamente y las variantes ya
implantadas son la corrección. Si ambas tasas son iguales, C6 se considera
descartada para la muestra y conviene conservar las variantes igualmente: el
coste está acotado por el timeout global y la caché.

## 5. Deuda técnica

* La confirmación empírica de C6 sigue pendiente de una ejecución autorizada del
  script live (tasa por variante y rate limits reales).
* El clasificador v1 puntúa alto algunas URLs legítimas canónicas (p. ej.
  `http://example.com/news` → `p≈0.57`). Por eso `ENABLE_V3_SCORING` nace en
  `false` y la activación queda supeditada a la guardia de regresión H5-T15.
* Sin `app_key`, el servicio depende del límite de tasa público de PhishTank; el
  script live cuantifica los 429 antes de recomendar una clave.
