# PLAN DE DESPLIEGUE CLOUD FREE-TIER Y OBSERVABILIDAD (v1.0)
## Proyecto: LinkGuard - Sistema Automatizado para la Evaluación de Riesgo de URLs
**Enfoque de Desarrollo:** Specification-Driven Development (SDD)  
**Estado:** Documento de Especificación Final - Fase 5  
**Presupuesto de Infraestructura:** $0 COP (Tier Gratuito Cloud)  

---

## 1. OBJETIVO Y ESTRATEGIA DE DESPLIEGUE CLOUD

Este documento establece la estrategia técnica para el despliegue, operación y observabilidad del prototipo **LinkGuard** en servicios de nube gratuitos (Free Tier), garantizando disponibilidad, seguridad, cero costos operativos y métricas de desempeño sin persistencia de datos personales.

---

## 2. ARQUITECTURA DE INFRAESTRUCTURA Y SERVICIOS CLOUD

### 2.1 Backend API (Python / FastAPI) — Render Web Service
* **Plataforma**: Render (Free Tier).
* **Mecanismo de Despliegue**: Contenedor Docker basado en `Dockerfile` multi-stage (`python:3.12-slim`).
* **Dominio Asignado**: Subdominio gratuito de Render Web Service.
* **Especificaciones del Recurso**:
  * RAM: 512 MB.
  * CPU: 0.1 vCPU compartida.
  * SSL/TLS: Certificado HTTPS automático emitido por Let's Encrypt.
  * Política de Inactividad (Cold Start): Suspensión automática del contenedor tras 15 minutos sin recibir peticiones. Reactivación automática ante nueva solicitud HTTP (tiempo de inicio en frío estimado: 15–30 segundos).

### 2.2 Frontend SPA (React / Vite) — Vercel
* **Plataforma**: Vercel (Hobby Free Tier).
* **Mecanismo de Despliegue**: Integración continua directa desde la rama `main` del repositorio `linkguard-frontend`.
* **Dominio Asignado**: Subdominio gratuito de Vercel.
* **Especificaciones del Recurso**:
  * Distribución: Edge Network Global (CDN).
  * SSL/TLS: Certificado HTTPS automático.
  * Ancho de Banda: 100 GB / mes.

---

## 3. CONFIGURACIÓN DE VARIABLES DE ENTORNO Y SECRETOS

### 3.1 Backend Variables (`linkguard-backend` en Render)
* `ENVIRONMENT`: `production`
* `PORT`: `10000`
* `CORS_ORIGINS`: Dominio del frontend en Vercel.
* `PHISHTANK_TIMEOUT`: `4.0`
* `PHISHTANK_TTL_SECONDS`: `7200`
* `RATE_LIMIT_PER_MINUTE`: `30`

### 3.2 Frontend Variables (`linkguard-frontend` en Vercel)
* `VITE_API_BASE_URL`: URL base de la API del backend en Render.

---

## 4. OBSERVABILIDAD Y LOGGING ESTRUCTURADO (JSON)

Para auditar el comportamiento del sistema sin utilizar bases de datos ni comprometer la privacidad del usuario:

### 4.1 Formato de Registro (JSON a `stdout`)
El backend emitirá cada evento a la salida estándar en formato JSON estructurado mediante la librería `structlog` o el logger nativo de Python.

### 4.2 Campos Estándar por Evento de Análisis (`ANALYZE_EVENT`)
```json
{
  "timestamp": "2026-10-16T10:30:00.123Z",
  "level": "INFO",
  "event_type": "URL_ANALYSIS_COMPLETED",
  "url_hash_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "score": 75,
  "risk_level": "Alto",
  "phishtank_status": "available",
  "rules_activated_count": 4,
  "execution_time_ms": 38.45,
  "client_ip_hash": "a1b2c3d4e5f6..."
}
```

---

## 5. SALUD DEL SERVICIO Y MANEJO DE COLD STARTS

### 5.1 Endpoint de Probe `/health`
* **Ruta**: `GET /health`
* **Respuesta**: `HTTP 200 OK`
* **Payload**:
  ```json
  {
    "status": "healthy",
    "service": "linkguard-api",
    "version": "1.0.0",
    "timestamp": "2026-10-16T10:30:00Z"
  }
  ```

### 5.2 Experiencia de Usuario ante Inicio en Frío (Cold Start)
En la interfaz React (`URLForm.jsx`), si la API no responde en los primeros 2 segundos (indicador de que el servidor de Render está despertando):
* La UI mostrará una notificación informativa: *"Conectando con el servidor de análisis (despertando instancia de prueba)... esto puede tomar unos segundos la primera vez."*
* Esto evita la sensación de bloqueo o frustración en el usuario.

---

## 6. BALANCE DE COSTOS OPERATIVOS

| Componente | Servicio / Proveedor | Costo Mensual |
| :--- | :--- | :---: |
| **Backend REST API** | Render Web Service (Free) | **$0 COP** |
| **Frontend SPA** | Vercel Hobby (Free) | **$0 COP** |
| **Certificados SSL/TLS** | Let's Encrypt / Vercel Edge | **$0 COP** |
| **Consultas PhishTank** | API Pública de Reputación | **$0 COP** |
| **Total Mensual** | **Infraestructura Cloud** | **$0 COP** |

---
**Aprobado para implementación bajo SDD (Specification-Driven Development).**
