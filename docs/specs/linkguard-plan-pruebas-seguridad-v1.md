# PLAN DE ASEGURAMIENTO DE CALIDAD (QA), PRUEBAS Y DEVSECOPS (v1.0)
## Proyecto: LinkGuard - Sistema Automatizado para la Evaluación de Riesgo de URLs
**Enfoque de Desarrollo:** Specification-Driven Development (SDD) / Test-Driven Development (TDD)  
**Documentos Relacionados:** `linkguard-especificacion-requisitos-v2.md` y `linkguard-especificacion-arquitectura-v1.md`  
**Estado:** Documento de QA Final - Fase 3  

---

## 1. INTRODUCCIÓN Y OBJETIVOS DE QA

Este documento especifica el **Plan Estratégico de Pruebas y Seguridad (DevSecOps)** para **LinkGuard**. Bajo el marco *Specification-Driven Development (SDD)*, cada caso de prueba mapea directamente contra un Requisito Funcional (RF), No Funcional (RNF) o Caso Borde (R-EDGE) previamente formalizado.

El objetivo principal es garantizar que el prototipo opere con **cero ejecuciones externas**, mantenga una latencia local $\le 50\text{ ms}$, resista fallos de red o *timeouts* en servicios de reputación externa y obtenga métricas objetivas de clasificación ($F1\text{-Score}$, $Precision$, $Recall$) utilizando una muestra estática etiquetada de **1,000 URLs (500 Maliciosas / 500 Legítimas)**.


---

## 2. ESTRATEGIA Y HERRAMIENTAS DE PRUEBA (PIRÁMIDE DE QA)

| Nivel de Prueba | Capa Objetivo | Herramienta Principal | Propósito Técnico |
| :--- | :--- | :--- | :--- |
| **Unitaria (Backend)** | Módulos de Reglas ($F01-F11$), Normalizador, Scoring | `pytest`, `pytest-cov` | Validar el comportamiento determinista de cada función pura. |
| **Unitaria (Frontend)** | Componentes React (`URLForm`, `ScoreCard`, etc.) | `vitest`, `React Testing Library` | Verificar renderizado, validación sintáctica local y estados of UI. |
| **Integración (Backend)** | API REST `/api/v1/analyze`, Reputación Client | `httpx`, `pytest-asyncio`, `respx` | Simular respuestas HTTP, manejar *timeouts* (4.0s) y degradación elegante. |
| **Seguridad (DevSecOps)** | Código fuente Python, JS y dependencias | Linter de Seguridad, Escaneo AST | Análisis estático y detección de dependencias no actualizadas. |
| **Experimental (QA)** | Algoritmo global de clasificación | Script de benchmarking en Python | Medir *Accuracy*, *Precision*, *Recall*, $F1\text{-Score}$ y latencia en dataset 500/500. |

| ID Caso de Prueba | RF Mapeado | Entradas de Prueba | Resultado Esperado | Criterio de Aceptación |
| :--- | :--- | :--- | :--- | :--- |
| **`TC-RF-101`** | `RF-101` | `"  http://example.com/demo  "` | `"http://example.com/demo"` | Limpieza de espacios al inicio/final. |
| **`TC-RF-102`** | `RF-102` | `"example.com/login-path"` | `"http://example.com/login-path"` | Asignación automática del esquema `http://` por defecto. |

| **`TC-RF-103`** | `RF-103` | `"https://example.com/path?q=1"` | Componentes atómicos extraídos | Parsing atómico correcto mediante librería estándar. |

| **`TC-RF-104`** | `RF-104` | Dominio IDN internacional | Identificación de Punycode | Conversión transparente de dominios internacionalizados. |
| **`TC-RF-105`** | `RF-105` | Cadena superior a la longitud límite | Respuesta HTTP 400 Bad Request | Detención inmediata indicando *"URL excede la longitud máxima procesable"*. |


### Módulo 200: Extracción de Características Léxicas y Estructurales (F01 - F11)

| ID Caso | Regla Mapeada | Cadena / Valor de Prueba | Resultado de Regla | Puntos Sumados | Criterio de Validación |
| :--- | :--- | :--- | :---: | :---: | :--- |
| **`TC-F01-P`** | `RF-201` (F01) | Cadena de 80 caracteres | `True` | **+10 pts** | Longitud $\ge 75$ activa penalización. |
| **`TC-F01-N`** | `RF-201` (F01) | Cadena de 45 caracteres | `False` | **0 pts** | Longitud $< 75$ no suma puntos. |
| **`TC-F02-P`** | `RF-202` (F02) | Dirección IP en host (`10.0.0.1`) | `True` | **+25 pts** | Detección explícita de IPv4 directa. |
| **`TC-F03-P`** | `RF-203` (F03) | Múltiples niveles de subdominio | `True` | **+10 pts** | Subdominios $\ge 3$ (excluyendo dominio raíz y TLD). |
| **`TC-F04-P`** | `RF-204` (F04) | Cadena de host con entropía $H(X) = 4.8$ | `True` | **+15 pts** | Entropía de Shannon del host $> 4.5$ bits/símbolo. |
| **`TC-F05-P`** | `RF-205` (F05) | Dominio de servicio acortador | `True` | **+15 pts** | Coincidencia en hashset de acortadores conocidos. |
| **`TC-F06-P`** | `RF-206` (F06) | Estructura con carácter `@` | `True` | **+20 pts** | Presencia del carácter `@` en la estructura de la URL. |
| **`TC-F07-P`** | `RF-207` (F07) | Dominio con múltiples guiones | `True` | **+8 pts** | Dos o más guiones en el nombre del dominio principal. |
| **`TC-F08-P`** | `RF-208` (F08) | Redirección de esquema en path/query | `True` | **+20 pts** | Subcadena de esquema dentro de path o query. |
| **`TC-F09-P`** | `RF-209` (F09) | Especificación de puerto no estándar | `True` | **+10 pts** | Puerto explícito distinto de 80 y 443. |
| **`TC-F10-P`** | `RF-210` (F10) | Ratio de caracteres especiales $> 15\%$ | `True` | **+7 pts** | Proporción de símbolos sobre longitud total. |
| **`TC-F11-P`** | `RF-211` (F11) | Presencia de palabras clave sensibles | `True` | **+15 pts** | Coincidencia con lista de términos sensibles. |


### Módulo 300: Algorithm Scoring, Clasificación y Explicabilidad

| ID Caso | Escenario de Prueba | Puntaje Calculado | Categoría de Riesgo | Evidencias Retornadas | Recomendación Asignada |
| :--- | :--- | :---: | :---: | :--- | :--- |
| **`TC-RF-301`** | URL limpia sin señales | **0 pts** | **Bajo** | Lista vacía `[]` | *"No se detectaron anomalías estructurales..."* |
| **`TC-RF-302`** | URL con F01 (+10) y F11 (+15) | **25 pts** | **Bajo** | `[F01_EXCESSIVE_LENGTH, F11_KEYWORDS]` | *"No se detectaron anomalías estructurales..."* |
| **`TC-RF-303`** | URL con F02 (+25) y F08 (+20) | **45 pts** | **Medio** | `[F02_DIRECT_IP, F08_SCHEMA_REDIRECT]` | *"El enlace presenta características inusuales..."* |
| **`TC-RF-304`** | URL con F02 (+25), F06 (+20), F08 (+20), F11 (+15) | **80 pts** | **Alto** | `[F02, F06, F08, F11]` | *"Enlace con elevado nivel de riesgo..."* |
| **`TC-RF-305`** | Suma teórica de reglas acoge 125 pts | **100 pts** | **Alto** | Reglas activadas mapeadas | El puntaje se acota estrictamente al techo de 100 pts. |

---

### Módulo 400: Concurrencia, Reputación Externa y Resiliencia

| ID Caso | Escenario de Prueba Reputación | Estado Servicio | Resultado Global | Criterio de Resiliencia |
| :--- | :--- | :---: | :---: | :--- |
| **`TC-RF-401`** | Respuesta en $200\text{ ms}$ (Encontrado en Lista Negra) | `"available"` | **+50 pts** (fuerza Nivel **Alto**) | Coincidencia suma 50 pts y asegura categoría de Riesgo Alto. |
| **`TC-RF-402`** | Respuesta en $150\text{ ms}$ (No encontrado) | `"available"` | Puntaje Léxico | No suma puntos extra; mantiene evaluación local. |
| **`TC-RF-403`** | API externa demora $> 4.0\text{ s}$ (Timeout) | `"timeout"` | Puntaje Léxico | Interrupción a los 4.0s; retorna HTTP 200 con fallback local. |
| **`TC-RF-404`** | API de reputación retorna error `HTTP 503` | `"unavailable"` | Puntaje Léxico | Captura silenciosa de la excepción; no genera error 500 al cliente. |
| **`TC-RF-405`** | Misma URL consultada 2 veces en $< 2\text{ horas}$ | `"cached"` | Inmediato ($< 1\text{ ms}$) | Recuperación directa desde la caché LRU volátil en RAM. |


---

## 4. MATRIZ DE CASOS DE PRUEBA PARA REQUISITOS NO FUNCIONALES (RNF)

| ID Caso | RNF Mapeado | Propiedad Evaluada | Método de Verificación | Criterio de Éxito |
| :--- | :--- | :--- | :--- | :--- |
| **`TC-RNF-101`**| `RNF-101` | **Aislamiento Absoluto de Red** | Monitoreo de sockets en pruebas de integración. | **Cero peticiones HTTP/TCP** dirigidas al host de la URL analizada. |
| **`TC-RNF-102`**| `RNF-102` | **Latencia Local Backend** | Benchmark interno con `time.perf_counter()`. | Tiempo de procesamiento local $T_{\text{local}} \le 50\text{ ms}$. |
| **`TC-RNF-103`**| `RNF-103` | **Arquitectura Stateless** | Verificación de sistema de archivos y proceso en Docker. | **Cero archivos creados/modificados** en disco durante la ejecución. |
| **`TC-RNF-104`**| `RNF-104` | **Uso de Memoria RAM** | Monitoreo de contenedor Docker con `docker stats`. | Consumo máximo de memoria RAM $\le 256\text{ MB}$ bajo carga nominal. |
| **`TC-RNF-105`**| `RNF-105` | **Rate Limiting Local** | 31 peticiones consecutivas desde la misma IP en $< 1\text{ min}$. | Petición 31 retorna `HTTP 429 Too Many Requests`. |

---

## 5. CASOS DE PRUEBA PARA CASOS BORDE Y EXCEPCIONES (R-EDGE)

| ID Caso | Escenario Borde | Entrada de Prueba | Comportamiento Esperado |
| :--- | :--- | :--- | :--- |
| **`TC-EDGE-01`** | Texto plano sin estructura de enlace | `"hola mundo este no es un link"` | **Cliente (React)**: Bloquea envío y muestra aviso. <br> **Backend**: Retorna `HTTP 400 Bad Request`. |
| **`TC-EDGE-02`** | Entrada sólo con espacios o vacía | `"   "` | **Cliente**: Inhabilita botón "Evaluar". |
| **`TC-EDGE-03`** | IP en notación hexadecimal u octal | Formato alternativo de IP | Normalización de IP a notación decimal estándar antes de F02. |
| **`TC-EDGE-04`** | URL con múltiples `@` encadenados | Estructura con `@` múltiples | Activación de F06 (+20 pts) y sanitización adecuada sin fallar. |

---

## 6. METODOLOGÍA DE EVALUACIÓN EXPERIMENTAL (DATASET 500/500)

Para dar cumplimiento a la validación empírica académica del prototipo:

### 6.1 Composición del Dataset Estático
* **Muestra No Confiable (Positivos - Class 1)**: $500$ URLs verificadas obtenidas de **PhishTank Feed**.
* **Muestra Legítima (Negativos - Class 0)**: $500$ dominios web legítimos obtenidos de **Tranco Top Sites**.
* **Total Muestra Evaluada**: $1,000$ URLs.

### 6.2 Matriz de Confusión y Fórmulas
| | Predicción No Confiable (Alto/Medio) | Predicción Legítimo (Bajo) |
| :--- | :---: | :---: |
| **Realidad No Confiable (PhishTank)** | **Verdadero Positivo (TP)** | **Falso Negativo (FN)** |
| **Realidad Legítimo (Tranco)** | **Falso Positivo (FP)** | **Verdadero Negativo (TN)** |

$$\text{Accuracy} = \frac{TP + TN}{TP + TN + FP + FN}$$

$$\text{Precision} = \frac{TP}{TP + FP}$$

$$\text{Recall} = \frac{TP}{TP + FN}$$

$$F1\text{-Score} = 2 \cdot \frac{\text{Precision} \cdot \text{Recall}}{\text{Precision} + \text{Recall}}$$

---

## 7. ESTRATEGIA DEVSECOPS Y ANÁLISIS ESTÁTICO DE SEGURIDAD

```text
[ Git Push / PR ] ──> [ GitHub Actions ] ──> [ Escaneo de Código Estático ]
                                         ──> [ Auditoría de Dependencias ]
                                         ──> [ Pytest & Vitest Suites ]
                                         ──> [ Docker Build Check ]
```

1. **Análisis Estático Backend (Python)**:
   * **Auditoría AST**: Escaneo de seguridad AST para detectar patrones no recomendados.
   * **Auditoría de Paquetes**: Verificación de versiones y dependencias en `requirements.txt`.
2. **Análisis Estático Frontend (React)**:
   * **Reglas Linter de Seguridad**: Verificación para prevenir inyecciones no deseadas o manipulación insegura del DOM.
   * **Auditoría de Dependencias**: Verificación de paquetes en el árbol de dependencias de Node.js.
3. **Gestión Estricta de Secretos**:
   * Cero credenciales o claves API escritas en código.
   * Uso exclusivo de archivos `.env` no subidos al repositorio (`.gitignore`).

---
**Aprobado para ejecución de Pruebas y Validación bajo SDD/TDD.**

