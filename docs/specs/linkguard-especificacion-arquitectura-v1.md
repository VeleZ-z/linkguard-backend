# Especificación de Arquitectura de Software

## 1. Módulos del Sistema
- Frontend: Aplicación web construida con React y Tailwind CSS.
- Backend: Servicio de API web construido con Python 3.12 y FastAPI.

## 2. Componentes de Interfaz
- Formulario de entrada con validación en cliente. Si el texto no corresponde a un formato válido de enlace o dominio, la interfaz detiene la solicitud y notifica al usuario.
- Panel de resultados con medidor de riesgo y recomendaciones de seguridad.
- Lista desplegable con el detalle de evidencias detectadas.

## 3. Servicios Backend
- Normalizador sintáctico de texto.
- Extractor modular de características mediante motor de reglas.
- Calculador de puntuación ponderada y niveles de clasificación.
- Cliente de consulta asíncrona a servicios de reputación externa con memoria caché.

## 4. Contratos de Comunicación
- Solicitud HTTP POST con objeto de datos conteniendo la cadena a analizar.
- Respuesta HTTP 200 con la puntuación calculada, nivel asignado y evidencias.
