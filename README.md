# LinkGuard — Backend API

Servicio REST en **Python 3.12 + FastAPI** que evalúa el riesgo de *phishing*
de una URL mediante análisis **sintáctico-léxico local** y consulta asíncrona
de reputación (**PhishTank**). Arquitectura **stateless in-memory**: sin base de
datos, sin persistencia de consultas y **sin conectarse nunca** a la URL
analizada (`RNF-101`).

> Estado: **Hito 1 en curso**. El scaffold (`H1-T01`) y la configuración
> centralizada (`H1-T02`) están listos; el endpoint `/api/v1/analyze` se
> implementa en tareas posteriores.

## Estructura del proyecto

```text
app/
├── main.py              # (H1-T08) aplicación FastAPI, CORS, rate limit y /health
├── config.py            # reexporta la configuración canónica (compatibilidad)
├── api/v1/              # controladores HTTP y router de la versión 1
├── schemas/             # DTOs Pydantic del contrato de API
├── core/                # configuración, errores y logging estructurado
├── normalization/       # normalizador sintáctico (RF-101…RF-105)
├── engine/              # modelos, pesos y reglas léxicas F01–F11
├── scoring/             # puntaje ponderado, evidencias y recomendaciones
├── clients/             # cliente asíncrono de PhishTank
├── cache/               # caché LRU volátil con TTL
└── services/            # orquestador concurrente del análisis
tests/
├── unit/                # pruebas unitarias (normalizador, reglas, scoring)
└── integration/         # pruebas HTTP con httpx.ASGITransport y respx
```

## Requisitos

- Python 3.12
- pip (o `uv`)

## Instalación local

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements-dev.txt
cp .env.example .env
```

## Variables de entorno

La configuración se valida con **Pydantic Settings** en
[`app/core/config.py`](app/core/config.py). La plantilla completa está en
`.env.example`:

| Variable | Por defecto | Descripción |
| :--- | :--- | :--- |
| `ENVIRONMENT` | `development` | `development`, `testing` o `production`. |
| `PORT` | `8000` | Puerto de escucha (Render usa `10000`). |
| `CORS_ORIGINS` | `http://localhost:5173` | Orígenes CORS separados por coma. |
| `PHISHTANK_TIMEOUT` | `4.0` | Timeout de la API de reputación (s). |
| `PHISHTANK_TTL_SECONDS` | `7200` | TTL de la caché LRU (s). |
| `RATE_LIMIT_PER_MINUTE` | `30` | Peticiones por minuto por IP. |
| `PHISHTANK_API_URL` | endpoint público | URL de consulta de PhishTank. |

`.env` real está excluido de Git.

En producción el contenedor arranca Uvicorn con `--proxy-headers
--forwarded-allow-ips='*'`, de modo que el rate limit se aplica por IP real del
cliente (cabecera `X-Forwarded-For` del proxy) y no por la IP del proxy.

## Comandos de verificación

```bash
ruff check .
ruff format --check .
bandit -r ./app -ll
pytest --cov=app --cov-report=term-missing --cov-fail-under=80
pip-audit
```

> La puerta de cobertura (`--cov-fail-under=80`) y el resto de la suite se
> activan a medida que se implementan las tareas del Hito 1.

## Documentación de referencia

Las especificaciones SDD viven en [`docs/specs/`](docs/specs/):

- `linkguard-especificacion-requisitos-v2.md` — RF/RNF, matriz de pesos y contrato §6.
- `linkguard-especificacion-arquitectura-v1.md` — arquitectura de capas.
- `linkguard-backend-estructura-directorio-v1.md` — árbol oficial de archivos.
- `linkguard-plan-pruebas-seguridad-v1.md` — casos `TC-*` y estrategia DevSecOps.
- `docs/specs/tasks/hito-1-backend-core-schemas.md` — checklist del Hito 1.

## Seguridad

- Cero peticiones HTTP hacia la URL ingresada por el usuario.
- Cero credenciales o *API keys* en el código: todo se lee del entorno.
- Logs en JSON con hash SHA-256 de URL e IP (nunca valores crudos).
- Dependencias auditadas con `pip-audit` y código con `bandit` en CI.
