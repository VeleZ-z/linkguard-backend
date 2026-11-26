# AGENTS.md — GUÍA PRINCIPAL PARA AGENTES DE CÓDIGO
## Proyecto: LinkGuard - Servicio Backend (FastAPI)
**Enfoque:** Specification-Driven Development (SDD)  
**Entorno de Ejecución:** Python 3.12 / FastAPI (Stateless In-Memory)  

---

## 1. VISIÓN DEL PROYECTO Y REGLAS INVIOLABLES

Este repositorio (`linkguard-backend`) contiene el servicio API REST de **LinkGuard**, encargado de la evaluación automatizada de riesgo de suplantación (*phishing*) en URLs mediante análisis sintáctico-léxico y consulta asíncrona de reputación.

Como agente de código (en cualquier rol: `build`, `tester`, `security-auditor`), **DEBES CUMPLIR ESTRICTAMENTE** las siguientes 6 reglas fundamentales (las 5 originales de los Hitos 1–3 más la regla ML del Hito 5):

1. **REGLA DE ORO DE AISLAMIENTO (RNF-101)**: **JAMÁS** escribas código que contacte el host de la URL analizada: nada de HTTP(S), TCP, DNS ni TLS contra el objetivo. El análisis es sintáctico-léxico local. Las consultas a **terceros** sobre el *dominio* (PhishTank, `RF-801`; RDAP solo si `RF-901`/H5-T17 se aprueba) **no** violan RNF-101, pero deben ser **opt-in por configuración** (`ENABLE_RDAP=false` por defecto). Solo PhishTank puede recibir la URL completa; RDAP, si se aprueba, recibe únicamente el dominio.
2. **OPERABILIDAD SIN ESTADO (RNF-103)**: El servicio opera 100% en memoria volátil RAM. No agregues bases de datos (SQLAlchemy, MongoDB, Redis externo) ni persistas registros de consultas en disco. Se **permiten artefactos de solo lectura** incluidos en la imagen (modelo, allowlist, blocklists, PSL: `RF-502`, `RF-504`, `RF-601`): se cargan al arranque y no se escriben en runtime.
3. **MOCKS OBLIGATORIOS EN PRUEBAS**: Toda prueba unitaria o de integración (`pytest`) que interactúe con el cliente de PhishTank **DEBE** usar `respx` o `pytest-mock`. Cero llamadas a APIs reales durante el test suite.
4. **MANEJO DE SECRETOS Y CONFIGURACIÓN**: Cero credenciales, claves API o tokens escritos en duro (*hardcoded*). Todas las configuraciones deben leerse mediante Pydantic `BaseSettings` (`app/core/config.py`) desde variables de entorno.
5. **RESILENCIA ANTE FALLOS EXTERNOS**: Si la API de PhishTank genera un *timeout* (4.0s) o error de red, el sistema **NUNCA** debe responder HTTP 500. Captura la excepción, devuelve el puntaje léxico local y establece `"phishtank_status": "timeout"`.
6. **CLASIFICADOR ML ACOTADO (Hito 5)**: solo se permite **un clasificador lineal interpretable** (regresión logística con hashing) entrenado **offline** y servido como JSON (`RF-602`, `RF-605`). La inferencia en producción es **Python puro** (sin NumPy/sklearn) y las dependencias de entrenamiento viven **solo** en `requirements-ml.txt`; **prohibido** añadirlas a `requirements.txt`. Nada de aprendizaje profundo ni LLM.

---

## 2. MAPA DE ESPECIFICACIONES Y DOCUMENTACIÓN (SDD)

Antes de generar o modificar cualquier módulo de código, **DEBES CONSULTAR** el archivo de especificación correspondiente en la carpeta `docs/specs/`:

* **Requisitos Funcionales y DTOs**: `docs/specs/linkguard-especificacion-requisitos-v2.md`
* **Adendo de Precisión y Robustez — Motor v3**: `docs/specs/linkguard-especificacion-accuracy-v3.md` (complementa a requisitos v2; prevalece **solo** donde su tabla de enmiendas §3 lo indica)
* **Laboratorio de referencia (solo lectura)**: `docs/specs/accuracy-lab/` (`README.md`, `RESULTS.md`, `data/`, `scripts/`)
* **Arquitectura de Capas y Patrón Pipeline**: `docs/specs/linkguard-especificacion-arquitectura-v1.md`
* **Plan de Pruebas y Casos Borde**: `docs/specs/linkguard-plan-pruebas-seguridad-v1.md`
* **Estructura de Directorios Oficiles**: `docs/specs/linkguard-backend-estructura-directorio-v1.md`
* **Checklists de Tareas por Hito**:
  * Hito 1: `docs/specs/tasks/hito-1-backend-core-schemas.md`
  * Hito 2: `docs/specs/tasks/hito-2-motor-reglas-lexicas.md`
  * Hito 3: `docs/specs/tasks/hito-3-phishtank-resiliencia.md`
  * Hito 5: `docs/specs/tasks/hito-5-accuracy-robustez.md`

**Protocolo de evaluación:** el §7 del adendo v3 **reemplaza** las cifras inconsistentes 500/500 (plan de pruebas) y 1 000/1 000 (requisitos v2). Toda medición de accuracy sigue ese protocolo: particiones agrupada por dominio, cruzada entre fuentes, temporal y negativos difíciles.

**Contrato congelado:** `POST /api/v1/analyze` es **INVARIANTE** (`v0.1.0-contract`, §6 de requisitos v2). No se agregan, quitan ni renombran campos; solo se añaden nuevos `rule_id` de evidencia (`RF-704`, `RF-803`…). El frontend no cambia.

---

## 3. ESTÁNDARES DE CÓDIGO Y ESTILO

* **Type Hints estricto**: Todas las funciones y métodos deben incluir tipado explicito de argumentos y retornos (Python 3.12 type hinting).
* **Validación con Pydantic v2**: Utilizar DTOs Pydantic con `Field` para validaciones sintácticas y descripciones.
* **Funciones Puras en Reglas**: Las 11 reglas de ciberseguridad (`app/engine/rules/f01` a `f11`) deben ser funciones puras independientes que tomen `ParsedURL` y retornen `RuleResult`.
* **Clasificador ML acotado (Hito 5)**: una sola regresión logística con hashing, entrenada offline y exportada a `app/engine/data/model_v1.json` (`RF-602`); inferencia en Python puro, sin NumPy/sklearn en producción. Dependencias de entrenamiento solo en `requirements-ml.txt` (`RF-605`), nunca en `requirements.txt`.
* **Artefactos de reputación**: JSON/binarios planos de solo lectura, sin `pickle`/`eval`/`exec` (`RNF-110`), con `manifest.json` y SHA-256 verificado al arranque; si falta o no coincide, arranque degradado sin HTTP 500 (`RF-506`, `RNF-107`).
* **Idioma de Comentarios y Docstrings**: Todo el código, comentarios y docstrings deben redactarse en español neutro (`es-419`).

---

## 4. COMANDOS DE VERIFICACIÓN Y AUDITORÍA

Ejecuta estos comandos en tu entorno local antes de dar por completada cualquier tarea:

```bash
# 1. Verificación de linter y formato con Ruff
ruff check .
ruff format --check .

# 2. Ejecución de la suite de pruebas unitarias e integración con cobertura
pytest --cov=app --cov-report=term-missing --cov-fail-under=80

# 3. Auditoría de seguridad de código estático (SAST)
bandit -r ./app -ll

# 4. Auditoría de dependencias conocidas
pip-audit
```

---

## 6. INTEGRACIÓN Y FLUJO CON OBSIDIAN (PKM VIA MCP) 
1. **Contextualización Inicial Obligatoria**: Antes de iniciar cualquier tarea o Historia de Usuario (HU), debes consultar las notas del Vault de Obsidian mediante el servidor MCP `obsidian` para alinear decisiones con la base de conocimiento personal. 
2. **Actualización al Finalizar (Post-Task / Post-HU)**: Al dar por completada una tarea importante, HU o Hito, debes crear o actualizar la nota correspondiente en el Vault de Obsidian registrando: 
- Estado de avance y tareas completadas. 
- Decisiones técnicas o de arquitectura tomadas. 
- Deuda técnica identificada o notas relevantes. 
- Respeta de forma estricta las convenciones, formatos y estructura de notas existentes en la PKM.

---

**Aprobado para la orquestación de agentes en OpenCode bajo SDD.**
