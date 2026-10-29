# AGENTS.md — GUÍA PRINCIPAL PARA AGENTES DE CÓDIGO
## Proyecto: LinkGuard - Servicio Backend (FastAPI)
**Enfoque:** Specification-Driven Development (SDD)  
**Entorno de Ejecución:** Python 3.12 / FastAPI (Stateless In-Memory)  

---

## 1. VISIÓN DEL PROYECTO Y REGLAS INVIOLABLES

Este repositorio (`linkguard-backend`) contiene el servicio API REST de **LinkGuard**, encargado de la evaluación automatizada de riesgo de suplantación (*phishing*) en URLs mediante análisis sintáctico-léxico y consulta asíncrona de reputación.

Como agente de código (en cualquier rol: `build`, `tester`, `security-auditor`), **DEBES CUMPLIR ESTRICTAMENTE** las siguientes 5 reglas fundamentales:

1. **REGLA DE ORO DE AISLAMIENTO (RNF-101)**: **JAMÁS** escribas código que realice conexiones HTTP (GET, POST, HEAD, WebSockets) hacia la URL que el usuario ingresa para analizar. El análisis es puramente sintáctico y léxico local.
2. **OPERABILIDAD SIN ESTADO (RNF-103)**: El servicio opera 100% en memoria volátil RAM. No agregues bases de datos (SQLAlchemy, MongoDB, Redis externo) ni persistas registros de consultas en disco.
3. **MOCKS OBLIGATORIOS EN PRUEBAS**: Toda prueba unitaria o de integración (`pytest`) que interactúe con el cliente de PhishTank **DEBE** usar `respx` o `pytest-mock`. Cero llamadas a APIs reales durante el test suite.
4. **MANEJO DE SECRETOS Y CONFIGURACIÓN**: Cero credenciales, claves API o tokens escritos en duro (*hardcoded*). Todas las configuraciones deben leerse mediante Pydantic `BaseSettings` (`app/core/config.py`) desde variables de entorno.
5. **RESILENCIA ANTE FALLOS EXTERNOS**: Si la API de PhishTank genera un *timeout* (4.0s) o error de red, el sistema **NUNCA** debe responder HTTP 500. Captura la excepción, devuelve el puntaje léxico local y establece `"phishtank_status": "timeout"`.

---

## 2. MAPA DE ESPECIFICACIONES Y DOCUMENTACIÓN (SDD)

Antes de generar o modificar cualquier módulo de código, **DEBES CONSULTAR** el archivo de especificación correspondiente en la carpeta `docs/specs/`:

* **Requisitos Funcionales y DTOs**: `docs/specs/linkguard-especificacion-requisitos-v2.md`
* **Arquitectura de Capas y Patrón Pipeline**: `docs/specs/linkguard-especificacion-arquitectura-v1.md`
* **Plan de Pruebas y Casos Borde**: `docs/specs/linkguard-plan-pruebas-seguridad-v1.md`
* **Estructura de Directorios Oficiles**: `docs/specs/linkguard-backend-estructura-directorio-v1.md`
* **Checklists de Tareas por Hito**:
  * Hito 1: `docs/specs/tasks/hito-1-backend-core-schemas.md`
  * Hito 2: `docs/specs/tasks/hito-2-motor-reglas-lexicas.md`
  * Hito 3: `docs/specs/tasks/hito-3-phishtank-resiliencia.md`

---

## 3. ESTÁNDARES DE CÓDIGO Y ESTILO

* **Type Hints estricto**: Todas las funciones y métodos deben incluir tipado explicito de argumentos y retornos (Python 3.12 type hinting).
* **Validación con Pydantic v2**: Utilizar DTOs Pydantic con `Field` para validaciones sintácticas y descripciones.
* **Funciones Puras en Reglas**: Las 11 reglas de ciberseguridad (`app/engine/rules/f01` a `f11`) deben ser funciones puras independientes que tomen `ParsedURL` y retornen `RuleResult`.
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
