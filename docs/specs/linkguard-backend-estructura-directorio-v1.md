# ESPECIFICACIÓN DE ESTRUCTURA Y ARQUITECTURA DE DIRECTORIOS (BACKEND)
## Repositorio: `linkguard-backend`
**Ruta Local:** `/home/v3le7/Documents/U/IntegradorI/linkguard/linkguard-backend/`  
**Stack Tecnológico:** Python 3.12 | FastAPI | Pydantic v2 | httpx | slowapi | Pytest | respx | Ruff | Bandit | Docker  
**Metodología:** Specification-Driven Development (SDD) & DevSecOps  
**Entorno de Agentes:** OpenCode (`build`, `tester`, `security-auditor`)  
**Estado:** Guía de Inicialización y Arquitectura para el Scaffold (Hito 1)

---

## 1. OBJETIVO Y PRINCIPIOS DE ORGANIZACIÓN

El presente documento establece la **topología de archivos y la estructura en capas** para el repositorio `linkguard-backend`. Esta organización ha sido diseñada para cumplir con los siguientes pilares:

1. **Desacoplamiento Estricto (Clean Layered Architecture)**: Separación clara entre controladores HTTP, esquemas DTO, normalización sintáctica, reglas léxicas atómicas, servicios de scoring, clientes de reputación y resiliencia.
2. **Compatibilidad Total con SDD y OpenCode**:
   - **`AGENTS.md` local**: Ingesta automática por OpenCode para guiar la ejecución de comandos, linters y pruebas.
   - **Carpetas `docs/specs/` locales**: Permite que los agentes lean los requisitos (`[RF-xxx]`, `[RNF-xxx]`) y las tareas atómicas mediante la herramienta `read` de forma directa sin alucinaciones.
3. **Soporte para DevSecOps y Containerización**:
   - Pipelines de CI/CD aislados con validación de estilo (`ruff`), análisis estático de seguridad (`bandit`), auditoría de dependencias (`pip-audit`) y cobertura mínima del 80% (`pytest-cov`).
   - Construcción multi-stage en Docker con imagen base `python:3.12-slim` y ejecutor no-root (`appuser`).

---

## 2. ÁRBOL COMPLETO DE DIRECTORIOS Y ARCHIVOS

```text
linkguard-backend/
├── AGENTS.md                       # Instrucciones y comandos para agentes de OpenCode en este repo
├── README.md                       # Documentación inicial y guía de desarrollo local
├── Dockerfile                      # Containerización multi-stage (python:3.12-slim, non-root)
├── .dockerignore                    # Archivos excluidos de la imagen Docker
├── .gitignore                      # Archivos excluidos de Git (.env, .venv, __pycache__, etc.)
├── .env.example                    # Plantilla de variables de entorno (pydantic-settings)
├── pyproject.toml                  # Configuración unificada de Ruff, Pytest, Coverage y Bandit
├── requirements.txt                # Dependencias de producción
├── requirements-dev.txt            # Dependencias de desarrollo, QA y DevSecOps
├── .github/
│   └── workflows/
│       └── backend-ci.yml          # Pipeline GitHub Actions (Linter + SAST + Pytest + Docker Build)
├── docs/                           # Especificaciones SDD espejo para lectura local de los agentes
│   ├── especificaciones-backend.md # Espejo condensado de RF/RNF, DTOs y Matriz de Pesos (w_i)
│   └── tasks/                      # Checklists atómicos por hito para seguimiento de los agentes
│       ├── hito-1-tasks.md
│       ├── hito-2-tasks.md
│       └── hito-3-tasks.md
├── app/                            # Código fuente de la aplicación
│   ├── __init__.py
│   ├── main.py                     # Punto de entrada FastAPI, CORS, slowapi, handlers y GET /health
│   ├── config.py                   # Centralización de variables de entorno con Pydantic BaseSettings
│   ├── api/
│   │   ├── __init__.py
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── router.py           # Enrutador principal de la API REST v1
│   │       └── analyze.py          # Controller HTTP: POST /api/v1/analyze
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── analyze.py              # DTOs Pydantic: AnalyzeRequest, AnalyzeResponse, EvidenceDTO, RiskLevel
│   ├── core/
│   │   ├── __init__.py
│   │   ├── errors.py               # Excepciones estructuradas (URLTooLongError, InvalidURLError)
│   │   └── logging.py              # Logging JSON estructurado (hash SHA-256 de URL/IP)
│   ├── normalization/
│   │   ├── __init__.py
│   │   └── normalizer.py           # RF-101..105: Sanitización, parsing 6 comp., percent/Punycode
│   ├── engine/
│   │   ├── __init__.py
│   │   ├── models.py               # Modelos internos: ParsedURL, RuleResult
│   │   ├── weights.py              # Matriz estática de pesos y penalizaciones w_i
│   │   ├── pipeline.py             # Pipeline determinista: run_rules(parsed_url) -> list[RuleResult]
│   │   ├── rules/                  # Módulos de reglas léxicas (Pipeline Pattern: 1 función por archivo)
│   │   │   ├── __init__.py
│   │   │   ├── registry.py         # Registro ordenado de las 11 funciones puras de reglas
│   │   │   ├── f01_excessive_length.py
│   │   │   ├── f02_direct_ip.py
│   │   │   ├── f03_multiple_subdomains.py
│   │   │   ├── f04_shannon_entropy.py
│   │   │   ├── f05_url_shortener.py
│   │   │   ├── f06_at_symbol.py
│   │   │   ├── f07_hyphens_in_domain.py
│   │   │   ├── f08_schema_redirect.py
│   │   │   ├── f09_non_standard_port.py
│   │   │   ├── f10_special_chars_ratio.py
│   │   │   └── f11_social_engineering_keywords.py
│   │   └── data/                   # Datasets y hashsets estáticos cargados en RAM
│   │       ├── __init__.py
│   │       ├── url_shorteners.py   # Hashset de dominios acortadores conocidos
│   │       └── sensitive_keywords.py # Set de palabras clave de suplantación de identidad
│   ├── scoring/
│   │   ├── __init__.py
│   │   ├── scorer.py               # RF-301/302: Suma ponderada min(100, sum(w_i)) y niveles de riesgo
│   │   ├── evidence.py             # RF-303: Generador de evidencias JSON explícitas (es-419)
│   │   └── recommendations.py      # RF-304: Generador de recomendaciones operativas por nivel
│   ├── clients/
│   │   ├── __init__.py
│   │   └── phishtank.py            # RF-401/402/404: Cliente HTTP httpx asíncrono con timeout y fallback
│   ├── cache/
│   │   ├── __init__.py
│   │   └── lru.py                  # RF-403: Caché volátil LRU en memoria RAM (TTL 2 horas)
│   └── services/
│       ├── __init__.py
│       └── analyzer.py             # RF-401: Orquestador concurrente (asyncio.gather local + PhishTank)
├── scripts/
│   └── benchmark_dataset.py        # Script para evaluación del dataset 500/500 (PhishTank/Tranco)
└── tests/                          # Suite completa de pruebas con Pytest
    ├── __init__.py
    ├── conftest.py                 # Fixtures globales y transportes mockeados de httpx/respx
    ├── unit/
    │   ├── __init__.py
    │   ├── test_normalizer.py      # Pruebas unitarias de RF-101..105 y R-EDGE-01..04
    │   ├── test_cache.py           # Pruebas de la caché LRU y expiración TTL
    │   ├── test_scorer.py          # Pruebas de scoring, tope 100 y mapeo de niveles
    │   ├── test_performance.py     # Pruebas de latencia local (<= 50 ms)
    │   └── rules/                  # Pruebas unitarias individuales para F01..F11
    │       ├── test_f01.py
    │       ├── test_f02.py
    │       ├── test_f03.py
    │       ├── test_f04.py
    │       ├── test_f05.py
    │       ├── test_f06.py
    │       ├── test_f07.py
    │       ├── test_f08.py
    │       ├── test_f09.py
    │       ├── test_f10.py
    │       └── test_f11.py
    └── integration/
        ├── __init__.py
        ├── test_analyze_endpoint.py # Pruebas HTTP del endpoint /api/v1/analyze
        ├── test_rate_limit.py      # RNF-105: Prueba de Rate Limiting (30 req/min/IP -> 429)
        ├── test_phishtank_resilience.py # RF-401..404 con respx (timeouts, 503, fallback)
        ├── test_network_isolation.py # RNF-101: Guardia de sockets (cero peticiones al host analizado)
        └── test_stateless.py       # RNF-103: Verificación de operabilidad sin escritura en disco
```

---

## 3. DESCRIPCIÓN DETALLADA DE COMPONENTES POR CAPA

### 3.1 Capa de Entrada y Controladores (`app/api/`)
* **`app/main.py`**: Inicializa la aplicación FastAPI, configura middlewares de CORS (restringido a dominios autorizados), monta `slowapi` para Rate Limiting (30 req/min/IP), registra controladores de errores globales (para no filtrar stack traces) y expone la ruta de monitoreo `GET /health`.
* **`app/api/v1/router.py`**: Router unificado para la versión 1 de la API.
* **`app/api/v1/analyze.py`**: Recibe la solicitud HTTP `POST /api/v1/analyze`, encomienda la validación de entrada a Pydantic y delega la ejecución al orquestador `services/analyzer.py`.

### 3.2 Capa de Esquemas y Contrato de Datos (`app/schemas/`)
* **`app/schemas/analyze.py`**: Define los DTOs Pydantic estrictos congelados en el Hito 1:
  - **`AnalyzeRequest`**: `url` (mínimo 3, máximo 4096 caracteres).
  - **`AnalyzeResponse`**: `url_analyzed`, `normalized_url`, `score` (0-100), `risk_level` (`Bajo`, `Medio`, `Alto`), `recommendation`, `evidences` (`list[Evidence]`), `phishtank_status`, `execution_time_ms`.
  - **`Evidence`**: `rule_id`, `points`, `title`, `description` (en español América Latina es-419).

### 3.3 Capa de Normalización Sintáctica (`app/normalization/`)
* **`app/normalization/normalizer.py`**: Implementa los requisitos `RF-101` a `RF-105`:
  - Limpieza de espacios y caracteres invisibles de control (` -`).
  - Anteposición del protocolo por defecto `http://` si carece de esquema.
  - Parsing sintáctico en 6 componentes (`scheme`, `netloc`, `path`, `params`, `query`, `fragment`).
  - Decodificación percentilada (`%XX`) y conversión de dominios internacionalizados (IDN) a Punycode (`xn--...`).
  - Retorno del objeto interno `ParsedURL`.

### 3.4 Motor de Reglas y Scoring (`app/engine/` y `app/scoring/`)
* **`app/engine/rules/f01_*.py` a `f11_*.py`**: Cada regla es una **función pura e independiente** que recibe `ParsedURL` y retorna `RuleResult(rule_id, activated, points, title, description)`.
* **`app/engine/rules/registry.py`**: Contiene la lista ordenada de las 11 funciones puras para ejecución determinista.
* **`app/engine/pipeline.py`**: Ejecuta las 11 reglas en secuencia local (tiempo \(\le 50	ext{ ms}\)).
* **`app/scoring/scorer.py`**: Aplica la suma ponderada \(	ext{Score} = \min(100, \sum w_i \cdot f_i)\), mapea los rangos (`Bajo: 0-30`, `Medio: 31-69`, `Alto: 70-100`) y genera la respuesta explicable.

### 3.5 Clientes de Reputación, Caché y Orquestador (`app/clients/`, `app/cache/`, `app/services/`)
* **`app/clients/phishtank.py`**: Cliente asíncrono con `httpx` para consultar la API de PhishTank con timeout configurable de 4.0 segundos y fallback silencioso (`phishtank_status: "timeout"` o `"unavailable"`).
* **`app/cache/lru.py`**: Caché LRU volátil en memoria RAM con TTL de 2 horas (7200 segundos) para almacenar respuestas externas recientes.
* **`app/services/analyzer.py`**: Orquestador principal que ejecuta en paralelo (`asyncio.gather`) la evaluación léxica local y la consulta a PhishTank, consolidando el resultado final.

---

## 4. ARCHIVO `AGENTS.MD` PARA EL REPOSITORIO BACKEND

Para que OpenCode opere con precisión dentro de `linkguard-backend/`, se debe incluir el siguiente archivo `AGENTS.md` en la raíz del repositorio backend:

```markdown
# AGENTS.md — linkguard-backend

## Contexto del Repositorio
Este repositorio contiene el servicio API REST de **LinkGuard** desarrollado en Python 3.12 y FastAPI.
Su función es evaluar el riesgo de phishing de URLs mediante análisis léxico determinista (11 reglas) y consulta asíncrona a PhishTank.
Enfoque de desarrollo: **Specification-Driven Development (SDD)**.

## Reglas Inviolables para Agentes
1. **AISLAMIENTO ABSOLUTO DE RED (RNF-101)**: Queda ESTRICTAMENTE PROHIBIDO escribir código que realice conexiones HTTP/GET/POST/sockets hacia la URL que el usuario ingresa para analizar.
2. **CERO PERSISTENCIA (RNF-103)**: No agregues bases de datos (SQL/NoSQL) ni escrituras de archivos en disco durante las solicitudes HTTP. El sistema opera 100% en memoria RAM.
3. **MOCKS OBLIGATORIOS EN TESTS**: Todas las pruebas unitarias e integración que involucren PhishTank DEBEN usar `respx` o `pytest-mock`. Prohibido el tráfico real a internet en el test suite.
4. **MANEJO DE SECRETOS**: No agregues credenciales ni URLs escritas en duro. Todo se configura mediante `app/config.py` (`Pydantic BaseSettings`).
5. **IDIOMA DE SALIDA (RNF-106)**: Los mensajes de error, títulos de evidencias, descripciones y recomendaciones deben estar formateados en español (América Latina, es-419).

## Comandos de Verificación
Ejecuta estos comandos en la terminal para validar tus cambios antes de dar por completada una tarea:

- **Ejecutar Linter**: `ruff check .`
- **Ejecutar Análisis de Seguridad SAST**: `bandit -r ./app -ll`
- **Ejecutar Suite de Pruebas**: `pytest`
- **Ejecutar Pruebas con Cobertura**: `pytest --cov=app --cov-report=term-missing`

## Referencias de Especificación Local
Antes de implementar un módulo, lee la especificación correspondiente usando la herramienta `read`:
- Requisitos y DTOs: `docs/specs/especificaciones-backend.md`
- Tareas de Hito 1: `docs/specs/tasks/hito-1-tasks.md`
- Tareas de Hito 2: `docs/specs/tasks/hito-2-tasks.md`
- Tareas de Hito 3: `docs/specs/tasks/hito-3-tasks.md`
```

---

## 5. GUÍA PASO A PASO PARA CREAR EL SCAFFOLD INICIAL (`H1-T01`)

Sigue esta secuencia de comandos para inicializar la estructura vacía en tu sistema:

```bash
# 1. Posicionarte en la carpeta del backend
cd /home/v3le7/Documents/U/IntegradorI/linkguard/linkguard-backend/

# 2. Crear el árbol de directorios fuente y de pruebas
mkdir -p app/api/v1 app/schemas app/core app/normalization app/engine/rules app/engine/data app/scoring app/clients app/cache app/services scripts
mkdir -p tests/unit/rules tests/integration
mkdir -p docs/specs/tasks
mkdir -p .github/workflows

# 3. Crear los archivos __init__.py vacíos para los paquetes de Python
touch app/__init__.py app/api/__init__.py app/api/v1/__init__.py app/schemas/__init__.py app/core/__init__.py app/normalization/__init__.py app/engine/__init__.py app/engine/rules/__init__.py app/engine/data/__init__.py app/scoring/__init__.py app/clients/__init__.py app/cache/__init__.py app/services/__init__.py
touch tests/__init__.py tests/unit/__init__.py tests/unit/rules/__init__.py tests/integration/__init__.py

# 4. Crear archivos base de configuración
touch README.md AGENTS.md Dockerfile .dockerignore .gitignore .env.example pyproject.toml requirements.txt requirements-dev.txt
```

---

### **Archivos de Dependencias Iniciales**

#### **`requirements.txt` (Producción)**
```text
fastapi>=0.110.0,<1.0.0
uvicorn[standard]>=0.28.0,<1.0.0
pydantic>=2.6.0,<3.0.0
pydantic-settings>=2.2.0,<3.0.0
httpx>=0.27.0,<1.0.0
slowapi>=0.1.9,<1.0.0
publicsuffix2>=2.20191221,<3.0.0
structlog>=24.1.0,<25.0.0
cachetools>=5.3.3,<6.0.0
```

#### **`requirements-dev.txt` (Desarrollo y QA)**
```text
pytest>=8.1.0,<9.0.0
pytest-cov>=4.1.0,<5.0.0
pytest-asyncio>=0.23.0,<1.0.0
respx>=0.21.0,<1.0.0
ruff>=0.3.0,<1.0.0
bandit>=1.7.8,<2.0.0
pip-audit>=2.7.0,<3.0.0
```

#### **`pyproject.toml` (Configuración de Ruff y Pytest)**
```toml
[tool.ruff]
target-version = "py312"
line-length = 100
select = ["E", "F", "W", "I", "N", "UP", "S", "B", "A", "C4", "T20"]
ignore = ["E501"]

[tool.ruff.per-file-ignores]
"tests/*" = ["S101"]

[tool.pytest.ini_options]
minversion = "8.0"
addopts = "-ra -q --cov=app --cov-report=term-missing --cov-fail-under=80"
testpaths = ["tests"]
asyncio_mode = "auto"
```

---

## 6. PRÓXIMOS PASOS CON OPENCODE

1. Ejecuta la secuencia de comandos de la **Sección 5** en tu terminal local para levantar el esqueleto inicial.
2. Abre OpenCode en la carpeta `/home/v3le7/Documents/U/IntegradorI/linkguard/linkguard-backend/`.
3. Selecciona el agente **`build`** (vía la tecla **Tab**).
4. Envía el prompt para la tarea **`H1-T02`** (Settings centralizados) y **`H1-T03`** (DTOs Pydantic).
5. Cambia al agente **`tester`** para verificar los DTOs y el normalizador (`H1-T07`).
6. Invoca al agente **`security-auditor`** al cierre del Hito 1 (`H1-T14`) para validar el cumplimiento de seguridad y aislamiento antes del primer *commit*.
