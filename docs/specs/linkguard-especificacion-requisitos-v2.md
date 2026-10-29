# ESPECIFICACIÓN FORMAL DE REQUISITOS Y ALCANCE (MVP v2.0)
## Proyecto: LinkGuard - Sistema Automatizado para la Evaluación de Riesgo de URLs
**Enfoque de Desarrollo:** Specification-Driven Development (SDD)  
**Estado:** Documento de Especificación Final - Versión 2.0  
**Arquitectura de Ejecución:** Stateless In-Memory (Sin Estado / Sin Base de Datos en MVP)  

---

## 1. INTRODUCCIÓN Y OBJETIVO DEL DOCUMENTO

Este documento constituye la **especificación técnica formal e inequívoca** para el desarrollo del MVP (Producto Mínimo Viable) del proyecto **LinkGuard**. Ha sido redactado bajo los principios de *Specification-Driven Development* (SDD) con el objetivo de servir como contrato estricto de entrada para desarrolladores humanos y agentes de inteligencia artificial orquestados.

El propósito central de LinkGuard es automatizar la evaluación preliminar de riesgo de suplantación de enlaces (*phishing*) en URLs ingresadas manualmente por usuarios finales, mediante el análisis sintáctico-léxico, un motor de reglas determinista de ciberseguridad y la consulta asíncrona de fuentes externas de reputación, sin ejecutar ni descargar el contenido de las páginas web evaluadas.

---

## 2. DELIMITACIÓN ESTRICTA DEL ALCANCE (SCOPE BOUNDARIES)

### 2.1 Dentro del Alcance (In-Scope - MVP v2.0)
1. **Interfaz de Usuario (Frontend SPA en React)**: Formulario para ingreso manual de URLs, visualización del puntaje de riesgo ($0-100$), nivel jerárquico de peligro, desglose de evidencias explícitas y recomendación orientadora.
2. **Servicio de Análisis (Backend REST en Python / FastAPI)**: API asíncrona stateless.
3. **Pipeline de Normalización**: Sanitización, stripping, inyección de protocolo por defecto, descomposición sintáctica (`scheme`, `netloc`, `path`, `params`, `query`, `fragment`), decodificación percentilada y conversión Unicode/Punycode.
4. **Motor de Extracción Léxica y Estructural**: Extracción puramente algorítmica de 11 características cuantitativas/booleanas ($F01 - F11$).
5. **Algoritmo de Suma Ponderada de Penalizaciones**: Asignación de pesos $w_i$ basados en el estado del arte de ciberseguridad, acotados en el rango $[0, 100]$.
6. **Mapeo de Categorías de Riesgo**: Clasificación en tres niveles (Bajo: $0-30$, Medio: $31-69$, Alto: $70-100$).
7. **Integración Asíncrona con PhishTank**: Consulta paralela no bloqueante mediante API REST con tiempo límite de espera (*timeout*) parametrizable (4.0s), caché volátil LRU en memoria RAM (TTL 2 horas) y modo degradado automático ante fallos de red o latencia.
8. **Explicabilidad**: Desglose transparente en formato JSON de cada regla activada con su respectivo puntaje aportado y descripción comprensible.

### 2.2 Fuera del Alcance (Out-of-Scope - Diferido a Versiones Futuras)
1. **Persistencia de Datos**: No se utilizarán bases de datos (SQL o NoSQL), almacenamiento en disco ni registro persistente de consultas o reseñas de usuarios en esta versión MVP.
2. **Ejecución e Inspección de Contenido Web**: Cero descargas de HTML, JavaScript, CSS, imágenes o ejecución remota de hipervínculos (cumplimiento estricto del aislamiento de seguridad).
3. **Mecanismos de Protección Antivirus/Malware**: No reemplaza software antivirus ni realiza escaneo de binarios ejecutables.
4. **Extensiones y Complementos**: No contempla extensiones de navegador, conectores para clientes de correo electrónico ni bots de mensajería instantánea.
5. **Gestión de Usuarios**: No incluye autenticación, roles, tokens JWT, perfiles ni historiales por usuario.
6. **Modelos de Aprendizaje Profundo / Consumo de LLMs en Runtime**: No se realizarán llamadas a modelos LLM para la clasificación de enlaces en el flujo principal del producto.

---

## 3. CATÁLOGO DE CARACTERÍSTICAS LÉXICAS Y MATRIZ DE PESOS ($w_i$)

La evaluación léxica se compone de 11 funciones puras e independientes. La siguiente tabla especifica la regla, la condición de activación, el peso asignado ($w_i$) y el sustento en ciberseguridad:

| ID | Nombre de la Característica | Criterio Técnico de Activación | Peso ($w_i$) | Sustento de Ciberseguridad |
| :--- | :--- | :--- | :---: | :--- |
| **MATCH_PT** | **Coincidencia PhishTank** | La URL completa o su host normalizado coincide con un registro activo en la API pública de PhishTank. | **+50 pts** *(Fuerza Nivel Alto)* | Confirmación directa por fuente pública de reputación de ciberseguridad. |
| **F02** | **Dirección IP Directa** | `netloc` corresponde a una dirección IPv4 (decimal, octal, hex) o IPv6. | **+25 pts** | Evita la resolución DNS legítima; altamente correlacionado con infraestructura maliciosa efímera. |
| **F06** | **Símbolo `@` en URL** | Presencia del carácter `@` en el host o path de la URL. | **+20 pts** | Provoca que los navegadores ignoren la cadena previa al `@` y se conecten al host posterior. |
| **F08** | **Desvío de Esquema en Path** | Presencia de las cadenas `http:` o `https:` dentro de `path` o `query`. | **+20 pts** | Intento de simular un dominio seguro o legítimo dentro de los parámetros de la URL. |
| **F11** | **Palabras Clave Sensibles** | Presencia de términos sensibles (`login`, `bank`, `verify`, `account`, `update`, `secure`, `signin`, `service`) en host/path/query. | **+15 pts** | Suplantación típica de portales de autenticación, banca en línea o servicios financieros. |
| **F05** | **Uso de Acortador de URL** | El dominio pertenece a una lista estática de servicios de acortamiento conocidos (ej. dominios acortadores en la base de reglas). | **+15 pts** | Ocultamiento deliberado de la dirección de destino real para evadir la inspección del usuario. |
| **F04** | **Entropía de Shannon Alta** | Entropía de información del host $H(X) = -\sum p(x) \log_2 p(x) > 4.5$ bits/símbolo. | **+15 pts** | Mide aleatoriedad en el nombre del dominio, característico de algoritmos DGA (*Domain Generation Algorithms*). |
| **F09** | **Puerto No Estándar** | Presencia explícita de un puerto en `netloc` diferente a 80 (HTTP) y 443 (HTTPS). | **+10 pts** | Tráfico canalizado a través de puertos de servicio inusuales para evadir filtros web estándar. |
| **F03** | **Subdominios Múltiples** | Conteo de niveles de subdominio $\ge 3$ (excluyendo TLD y dominio principal). | **+10 pts** | Uso de subdominios profundos para incrustar nombres de marcas legítimas dentro de dominios de terceros. |
| **F01** | **Longitud Excesiva de URL** | Longitud total de la cadena normalizada $\ge 75$ caracteres. | **+10 pts** | Inclusión de tokens largos, parámetros de evasión o cadenas de relleno (*URL padding*). |
| **F07** | **Guiones en Nombre de Dominio** | Presencia de 2 o más guiones (`-`) en el nombre del dominio principal. | **+8 pts** | Técnica de *typosquatting* o *combo-squatting* imitando nombres comerciales legítimos. |
| **F10** | **Ratio de Caracteres Especiales** | Proporción de caracteres (`?`, `=`, `%`, `-`, `_`, `&`) respecto a la longitud total $> 15\%$. | **+7 pts** | Inundación de parámetros y codificaciones complejas utilizadas en vectores de ataque por redirección. |

---

## 4. REQUISITOS FUNCIONALES GRANULARES (RF)

### Módulo 100: Recepción, Normalización y Sanitización de Entrada
* **`RF-101` Sanitización de Cadena**: El sistema debe recibir la URL enviada por el usuario, aplicar stripping de espacios al inicio/final, eliminar caracteres invisibles de control (`\x00-\x1F`, `\x7F`) y rechazar códigos de inyección.
* **`RF-102` Inyección de Protocolo por Defecto**: Si la URL ingresada carece de esquema explícito (ej. `example.com/login`), el sistema debe anteponer `http://` para permitir el correcto parsing sintáctico.
* **`RF-103` Parsing Sintáctico Atómico**: El sistema debe descomponer la URL utilizando la librería estándar (`urllib.parse`) en exactamente 6 componentes: `scheme`, `netloc`, `path`, `params`, `query` y `fragment`.
* **`RF-104` Decodificación y Normalización Unicode/Punycode**:
  * Decodificar secuencias de escape percentiladas (`%XX`).
  * Transformar dominios internacionalizados (IDN) a su representación Punycode (`xn--...`) para identificar ataques de homógrafos (caracteres cirílicos/griegos).
* **`RF-105` Control de Longitud Máxima de Entrada**: Si la URL ingresada supera los **4096 caracteres**, el sistema debe interrumpir la ejecución y retornar un error sintáctico estructurado `HTTP 400 Bad Request` indicando *\"URL excede la longitud máxima procesable (4096 caracteres)\"*.

### Módulo 200: Extracción de Características Léxicas y Estructurales
* **`RF-201` [F01] Evaluación de Longitud**: Retornar `True` si la longitud total de la URL es $\ge 75$ caracteres.
* **`RF-202` [F02] Evaluación de IP Directa**: Evaluar si el campo `netloc` (removiendo puerto) constituye una dirección IPv4 o IPv6 válida (en notación decimal, octal o hexadecimal).
* **`RF-203` [F03] Evaluación de Subdominios**: Extraer el dominio raíz y TLD usando la especificación de la *Public Suffix List*. Contar los niveles jerárquicos restantes y retornar `True` si el conteo es $\ge 3$.
* **`RF-204` [F04] Cálculo de Entropía de Shannon**: Calcular la entropía sobre el nombre del host mediante la fórmula:
  $$H(X) = -\sum_{i=1}^{n} P(x_i) \log_2 P(x_i)$$
  Retornar `True` si $H(X) > 4.5$.
* **`RF-205` [F05] Detección de Acortador**: Contrastar el host normalizado contra una lista estática hashset de dominios acortadores conocidos. Retornar `True` en caso de coincidencia.
* **`RF-206` [F06] Detección de Símbolo `@`**: Inspeccionar la presencia del carácter `@` dentro de la estructura de la URL.
* **`RF-207` [F07] Evaluación de Guiones en Dominio**: Contar la ocurrencia del carácter `-` en el nombre del dominio principal. Retornar `True` si el conteo es $\ge 2$.
* **`RF-208` [F08] Detección de Desvío de Esquema**: Inspeccionar los campos `path` y `query` en búsqueda de las subcadenas `http:` o `https:`.
* **`RF-209` [F09] Evaluación de Puertos No Estándar**: Verificar si `netloc` incluye un puerto explícito diferente a 80 y 443.
* **`RF-210` [F10] Ratio de Caracteres Especiales**: Calcular la proporción $\frac{\text{Conteo}(?, =, %, -, \_, \&)}{\text{Longitud Total de la URL}}$. Retornar `True` si la proporción es $> 0.15$ ($15\%$).
* **`RF-211` [F11] Coincidencia de Palabras Clave Sensibles**: Buscar coincidencias insensibles a mayúsculas/minúsculas de términos de suplantación (`login`, `bank`, `verify`, `account`, `update`, `secure`, `signin`, `service`) en la URL.

### Módulo 300: Algoritmo de Scoring, Clasificación y Explicabilidad
* **`RF-301` Cálculo de Puntaje Ponderado**: Sumar las penalizaciones de las reglas activadas según la fórmula:
  $$\text{Score Total} = \min\left(100, \sum_{i=1}^{n} w_i \cdot f_i(\text{URL})\right)$$
* **`RF-302` Mapeo de Niveles de Riesgo**: Categorizar el puntaje final redondeado en tres niveles:
  * **Riesgo Bajo**: $0 \le \text{Score} \le 30$.
  * **Riesgo Medio**: $31 \le \text{Score} \le 69$.
  * **Riesgo Alto**: $70 \le \text{Score} \le 100$.
* **`RF-303` Desglose de Evidencias Granulares**: Generar un arreglo JSON de evidencias estructuradas. Cada elemento debe incluir:
  * `rule_id`: Código de la regla (ej. `\"F02_DIRECT_IP\"`).
  * `points`: Puntos sumados (ej. `25`).
  * `title`: Título técnico legible de la anomalía.
  * `description`: Explicación en español neutro comprensible para el usuario final.
* **`RF-304` Generación de Recomendación de Seguridad**: Asociar una recomendación operativa al nivel de riesgo asignado:
  * **Bajo**: *\"No se detectaron anomalías estructurales severas ni reportes en listas negras. Mantenga las precauciones habituales al navegar.\"*
  * **Medio**: *\"El enlace presenta características inusuales o sospechosas (ej. longitud elevada, palabras clave o acortadores). Verifique la identidad del remitente antes de interactuar.\"*
  * **Alto**: *\"Enlace altamente peligroso o reportado activamente como sospechoso. Se recomienda NO hacer clic, NO ingresar credenciales ni compartir información confidencial.\"*

### Módulo 400: Concurrencia, Reputación y Resiliencia
* **`RF-401` Ejecución Paralela No Bloqueante**: Ejecutar el motor de reglas léxicas local y la consulta a la API REST de PhishTank de forma concurrente mediante `asyncio.gather`.
* **`RF-402` Control de Timeout Parametrizado**: Establecer un tiempo límite máximo de espera para la API externa mediante la variable de entorno `PHISHTANK_TIMEOUT` (valor por defecto ajustado: **4.0 segundos**).
* **`RF-403` Caché Volátil en Memoria (LRU)**: Almacenar las respuestas de PhishTank en una caché LRU en memoria RAM con un TTL (*Time-To-Live*) optimizado de **7200 segundos (2 horas)** para maximizar la reutilización de consultas recientes.
* **`RF-404` Manejo de Modo Degradado Elegante**: Si la API de PhishTank genera un *timeout* o error de red ($5xx/4xx$), el backend debe capturar la excepción de forma silenciosa, calcular el nivel de riesgo basándose en las reglas léxicas locales y devolver el atributo `\"phishtank_status\": \"timeout\"` o `\"unavailable\"`, garantizando un código HTTP 200 al cliente.
* **`RF-405` Elevación de Riesgo por Reputación**: Si PhishTank confirma que la URL está registrada en su lista negra activa, el motor debe asignar +50 puntos adicionales, forzando la clasificación a **Riesgo Alto**.

---

## 5. REQUISITOS NO FUNCIONALES GRANULARES (RNF)

* **`RNF-101` Aislamiento Absoluto de Red (Cero Ejecución)**: El backend de LinkGuard jamás realizará peticiones HTTP GET, POST o HEAD hacia la URL que el usuario solicita analizar, ni descargará archivos HTML/JS ni conectará con el servidor de destino.
* **`RNF-102` Tiempo de Respuesta Local**: El cálculo de la extracción de características $F01-F11$ y la evaluación de la matriz de reglas en el backend debe tomar $\le 50\text{ ms}$.
* **`RNF-103` Operabilidad Sin Estado (Stateless Architecture)**: El sistema operará 100% en memoria volátil RAM. No se requerirá base de datos relacional, NoSQL ni archivos de almacenamiento en disco para procesar peticiones.
* **`RNF-104` Despliegue en Cloud Free-Tier**: El contenedor backend en FastAPI debe ser optimizado para ejecutarse en entornos Docker restringidos a **256 MB - 512 MB de RAM** (planes gratuitos de Render, Railway o Vercel).
* **`RNF-105` Seguridad e Interoperabilidad API (CORS & Rate Limiting)**:
  * **CORS**: Configurar middleware de CORS restringido para permitir peticiones únicamente desde el dominio del frontend desplegado.
  * **Rate Limiting Local**: Aplicar un límite preventivo en memoria de **30 peticiones por minuto por dirección IP** (`slowapi` / `limits`) para mitigar abusos sobre la infraestructura gratuita.
* **`RNF-106` Formato y Codificación de Respuestas**: Todas las respuestas de la API deben ser entregadas en formato JSON estandarizado, codificadas en UTF-8 y con mensajes en idioma español (América Latina).

---

## 6. ESPECIFICACIÓN DEL CONTRATO DE INTERFAZ (API REST DTOs)

### 6.1 Endpoint de Análisis
* **Método HTTP**: `POST`
* **Ruta de Acceso**: `/api/v1/analyze`
* **Encabezados Requeridos**: `Content-Type: application/json`

### 6.2 Esquema del Request (Solicitud JSON)
```json
{
  "url": "string (Requerido, mín: 3, máx: 4096 caracteres)"
}
```

### 6.3 Esquema del Response (Respuesta JSON HTTP 200 OK)
```json
{
  "url_analyzed": "https://subdomain.example.com/login-path",
  "normalized_url": "http://subdomain.example.com/login-path",
  "score": 75,
  "risk_level": "Alto",
  "recommendation": "Enlace highly peligroso o reportado activamente como sospechoso. Se recomienda NO hacer clic, NO ingresar credenciales ni compartir información confidencial.",
  "evidences": [
    {
      "rule_id": "F11_SOCIAL_ENGINEERING_KEYWORDS",
      "points": 15,
      "title": "Palabras clave de ingeniería social",
      "description": "Se detectaron términos sensibles asociados a suplantación de identidad (login, verify, account)."
    },
    {
      "rule_id": "F03_MULTIPLE_SUBDOMAINS",
      "points": 10,
      "title": "Niveles excesivos de subdominios",
      "description": "El enlace utiliza múltiples niveles de subdominios para simular un sitio legítimo."
    },
    {
      "rule_id": "F01_EXCESSIVE_LENGTH",
      "points": 10,
      "title": "Longitud inusualmente larga",
      "description": "La URL contiene más de 75 caracteres, superando el umbral estándar."
    },
    {
      "rule_id": "MATCH_PHISHTANK",
      "points": 50,
      "title": "Reporte en lista negra de PhishTank",
      "description": "La URL se encuentra confirmada como maliciosa en la base de datos pública de PhishTank."
    }
  ],
  "phishtank_status": "available",
  "execution_time_ms": 42.15
}
```

---

## 7. PLAN DE PRUEBAS Y VALIDACIÓN EXPERIMENTAL (QA & DATASET)

Para validar objetivamente el desempeño del sistema bajo el indicador de cumplimiento estipulado en la metodología académica del proyecto:

1. **Conjunto de Datos Etiquetado (Dataset de Evaluación)**:
   * **Muestra de Phishing (Positivos)**: $1,000$ URLs verificadas activas extraídas del feed público de **PhishTank**.
   * **Muestra Legítima (Negativos)**: $1,000$ dominios web populares extraídos de la lista **Tranco Top Sites**.
2. **Métricas de Clasificación a Reportar**:
   * $Accuracy = \frac{TP + TN}{TP + TN + FP + FN}$
   * $Precision = \frac{TP}{TP + FP}$
   * $Recall = \frac{TP}{TP + FN}$
   * $F1-Score = 2 \cdot \frac{Precision \cdot Recall}{Precision + Recall}$
3. **Métrica de Latencia**: Medición del tiempo medio de respuesta global ($T_{\text{medio}}$) desagregado entre análisis local y consulta de reputación.

---
**Aprobado para implementación bajo SDD (Specification-Driven Development).**
