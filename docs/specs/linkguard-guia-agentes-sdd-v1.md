# GUÍA DE ORQUESTACIÓN Y PAUTAS PARA AGENTES DE IA EN SDD (v1.0)
## Proyecto: LinkGuard - Sistema Automatizado para la Evaluación de Riesgo de URLs
**Enfoque de Desarrollo:** Specification-Driven Development (SDD)  
**Estado:** Documento de Especificación Final - Fase 6  
**Estrategia de Agentes:** Asistencia en Tiempo de Desarrollo (Dev-Time Only) / Cero Agentes en Runtime  

---

## 1. PRINCIPIOS FUNDAMENTALES Y ROL DE LA IA EN LINKGUARD

Para evitar el "ruido", la latencia no determinista y la sobreingeniería asociada al uso inadecuado de modelos de lenguaje:

1. **Cero LLMs/Agentes en Tiempo de Ejecución (Runtime Isolation)**: El producto en producción evalúa URLs mediante algoritmos deterministas y consultas HTTP estructuradas. No invoca APIs de LLMs ni orquestadores tipo LangChain/CrewAI para la clasificación.
2. **Desarrollo Guiado por Especificación (SDD)**: Los agentes de IA se emplean exclusivamente durante la fase de construcción de código (tiempo de desarrollo). La especificación técnica (`.md`) actúa como contrato estricto: los agentes no pueden inventar características, agregar bases de datos ni incluir dependencias no documentadas.
3. **Roles Especializados de Agentes (Simulación de Equipo)**: Inspirado en marcos colaborativos (AgentMesh), se dividen las responsabilidades de desarrollo entre roles de IA desacoplados.

---

## 2. TAXONOMÍA Y ROLES DE AGENTES EN TIEMPO DE DESARROLLO

```text
[ ESPECIFICACIÓN SDD (.md) ]
         │
         ├──► [ Agente Planificador / Arquitecto ] ──► Fragmentación en Tareas Atómicas
         │
         ├──► [ Agente Programador (Coder) ]       ──► Implementación de Módulos (FastAPI / React)
         │
         ├──► [ Agente Tester (QA) ]               ──► Generación de Pruebas (Pytest / Vitest)
         │
         └──► [ Agente Revisor / Seguridad ]      ──► Auditoría SAST (Bandit, ESLint, Hardening)
```

### 2.1 Agente Planificador / Arquitecto
* **Función**: Leer los archivos de especificación (`linkguard-especificacion-requisitos-v2.md` y `linkguard-especificacion-arquitectura-v1.md`) y fragmentar el trabajo en tareas atómicas independientes.
* **Entregables**: Listas de tareas en markdown para ejecución secuencial.

### 2.2 Agente Programador (Coder Agent - Cursor/Copilot/Claude/Gemini)
* **Función**: Escribir el código fuente para una única función de regla ($F01-F11$), DTO o componente React.
* **Regla de Oro**: Debe recibir como contexto el DTO exacto y el requisito $RF-XXX$. Está prohibido modificar la interfaz expuesta.

### 2.3 Agente Tester (QA Agent)
* **Función**: Generar la suite de pruebas unitarias basadas en el documento `linkguard-plan-pruebas-seguridad-v1.md`.
* **Regla de Oro**: Diseñar mocks estrictos para la API de PhishTank sin realizar peticiones salientes a internet durante el test suite.

### 2.4 Agente Revisor y Auditor de Seguridad
* **Función**: Inspeccionar el código generado antes de cada *Pull Request*.
* **Criterios de Rechazo**:
  * Código que intente hacer peticiones `HTTP GET/POST` a la URL analizada por el usuario (violación de aislamiento).
  * Inclusión de credenciales o claves API escritas en duro (*hardcoded*).
  * Adición de librerías de componentes pesadas no autorizadas en el frontend.

---

## 3. PROTOCOLO DE PROMPTING BASADO EN ESPECIFICACIÓN (SDD)

Para solicitar código a un agente de IA sin generar alucinaciones, la estructura del *prompt* debe seguir el siguiente patrón estándar:

```text
CONTEXTO:
Eres un Agente Programador en LinkGuard. Debes implementar la regla [RF-202 / F02].
Consulta la especificación oficial en `linkguard-especificacion-requisitos-v2.md`.

RESTRICCIONES:
1. Crea una función pura `evaluate_direct_ip(parsed_url: ParsedURL) -> RuleResult`.
2. Utiliza la librería estándar `ipaddress` de Python.
3. No agregues llamadas de red ni dependencias externas.
4. Incluye type hints y docstrings en español neutro.

ENTRADA DE PRUEBA ESPERADA:
- Dominio con IP: "192.168.1.1" -> RuleResult(activated=True, points=25)
- Dominio con Host: "example.com" -> RuleResult(activated=False, points=0)
```

---

## 4. CICLO DE RETROALIMENTACIÓN TIPO DEBUGGER AUTOMÁTICO

Cuando un agente genere código que no pase las pruebas automatizadas:

1. **Captura de Stack Trace**: Extraer la salida exacta de `pytest` o `vitest`.
2. **Re-prompting de Corrección**: Enviar el código defectuoso junto con el fallo de la prueba al agente de IA con la instrucción: *"El código no satisface el caso de prueba TC-RF202-01. Ajusta la lógica sin modificar la firma del método."*
3. **Iteración Máxima**: Limitar las iteraciones automáticas a 3 intentos. Si persiste el fallo, intervención manual del desarrollador humano.

---
**Aprobado para implementación bajo SDD (Specification-Driven Development).**
