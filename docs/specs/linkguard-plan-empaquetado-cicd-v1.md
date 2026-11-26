# PLAN DE EMPAQUETADO E INTEGRACIÓN CONTINUA (DOCKER & CI/CD)
## Proyecto: LinkGuard - Sistema Automatizado para la Evaluación de Riesgo de URLs
**Enfoque de Desarrollo:** Specification-Driven Development (SDD) & DevSecOps  
**Estado:** Especificación Técnica Formal - Fase 4  
**Estructura de Repositorios:** Dos Repositorios Independientes (`linkguard-backend` y `linkguard-frontend`)  
**Estrategia de Ramas:** GitHub Flow (`main` + `feature/*`)  

---

## 1. ESTRATEGIA DE REPOSITORIOS Y FLUJO DE TRABAJO EN GIT

### 1.1 Estructura de Repositorios Independientes
Para mantener un desacoplamiento estricto y permitir ciclos de despliegue autónomos, el proyecto se divide en dos repositorios independientes en GitHub:

1. **`linkguard-backend`**:
   * Contiene el código fuente en Python 3.12 / FastAPI, motor de reglas ($F01-F11$), cliente de PhishTank, pruebas con `pytest` y configuración de containerización para el servicio API REST.
2. **`linkguard-frontend`**:
   * Contiene la aplicación SPA en React + Vite + Tailwind CSS, validaciones sintácticas del cliente, pruebas con `vitest` y configuración de containerización basada en Nginx.

### 1.2 Estrategia de Ramas: GitHub Flow
Se adopta la metodología **GitHub Flow** por su sencillez, agilidad y compatibilidad con agentes de IA orchestrados:

* **`main`**: Rama principal y siempre en estado desplegable (*production-ready*). Ningún desarrollador ni agente realiza *commits* directos sobre `main`.
* **`feature/*`**: Ramas efímeras creadas para la implementación de características específicas (ej. `feature/f04-shannon-entropy`, `feature/url-form-component`).
* **`fix/*`**: Ramas para la corrección de errores sintácticos o de lógica (ej. `fix/punycode-decoder-edge-case`).
* **Reglas de Integración (Pull Requests)**:
  * Todo cambio debe integrarse mediante un *Pull Request* (PR) hacia `main`.
  * La fusión (*merge*) requiere la aprobación de la suite automatizada de CI/CD (todos los *checks* en verde).

---

## 2. SPECIFICACIÓN DE CONTAINERIZACIÓN CON DOCKER (MULTI-STAGE BUILDS)

### 2.1 Backend Containerization (`linkguard-backend/Dockerfile`)
El empaquetado del servicio API en FastAPI utiliza un patrón *multi-stage* basado en `python:3.12-slim` para minimizar la superficie de ataque y reducir el tamaño de la imagen ($< 180\text{ MB}$).

```dockerfile
# STAGE 1: Builder (Instalación de dependencias)
FROM python:3.12-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# STAGE 2: Execution Runtime (Imagen final liviana y segura)
FROM python:3.12-slim AS runner

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    PORT=8000

WORKDIR /app

# Crear usuario no privilegiado (Non-Root User)
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /bin/sh appuser

COPY --from=builder /opt/venv /opt/venv
COPY --chown=appuser:appgroup ./app /app/app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 2.2 Frontend Containerization (`linkguard-frontend/Dockerfile`)
El empaquetado de la interfaz SPA utiliza un patrón *multi-stage* compilando los assets con Node.js y sirviéndolos mediante un servidor web Nginx sobre Alpine Linux ($< 25\text{ MB}$).

```dockerfile
# STAGE 1: Compilation Build
FROM node:20-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

# STAGE 2: Web Server Runtime (Nginx Alpine)
FROM nginx:alpine AS runner

# Copiar archivos compilados estáticos
COPY --from=builder /app/dist /usr/share/nginx/html

# Configuración personalizada de Nginx para SPA y cabeceras de seguridad
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s \
  CMD wget -qO- http://localhost/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
```

#### Configuración de Nginx para SPA (`linkguard-frontend/nginx.conf`)
```nginx
server {
    listen 80;
    server_name localhost;

    location / {
        root /usr/share/nginx/html;
        index index.html index.htm;
        try_files $uri $uri/ /index.html;
    }

    # Cabeceras de Seguridad Básicas (Hardening HTTP)
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
}
```

---

## 3. PIPELINES DE INTEGRACIÓN CONTINUA (GITHUB ACTIONS)

### 3.1 Workflow del Backend (`linkguard-backend/.github/workflows/backend-ci.yml`)

Este pipeline se activa automáticamente en cada *push* a `main` o *Pull Request*:

```yaml
name: LinkGuard Backend CI

on:
  push:
    branches: [ "main" ]
  pull_request:
    branches: [ "main" ]

jobs:
  lint-and-sast:
    name: Code Quality & Security Audit
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python 3.12
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install ruff bandit pip-audit

      - name: Run Ruff (Linter)
        run: ruff check .

      - name: Run Bandit (Security Static Analysis)
        run: bandit -r ./app -ll

      - name: Audit Dependencies (Supply-Chain Security)
        run: pip-audit --ignore-code 1

  test:
    name: Unit & Integration Tests
    needs: lint-and-sast
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python 3.12
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          pip install pytest pytest-cov httpx respx

      - name: Run Pytest Suite with Coverage
        run: pytest --cov=app --cov-report=term-missing --cov-fail-under=80

  docker-build:
    name: Docker Build Check
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Build Docker Image
        uses: docker/build-push-action@v5
        with:
          context: .
          push: false
          tags: linkguard-backend:test
```

### 3.2 Workflow del Frontend (`linkguard-frontend/.github/workflows/frontend-ci.yml`)

```yaml
name: LinkGuard Frontend CI

on:
  push:
    branches: [ "main" ]
  pull_request:
    branches: [ "main" ]

jobs:
  lint-and-test:
    name: Quality & Unit Tests
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Node.js 20
        uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"

      - name: Install Dependencies
        run: npm ci

      - name: Run ESLint
        run: npm run lint

      - name: Run Vitest Suite
        run: npm run test:run

  docker-build:
    name: Docker Build Check
    needs: lint-and-test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Build Docker Image
        uses: docker/build-push-action@v5
        with:
          context: .
          push: false
          tags: linkguard-frontend:test
```

---

## 4. SEGURIDAD EN LA CADENA DE SUMINISTRO (DEVSECOPS INTEGRATED)

1. **Escaneo de Vulnerabilidades en Dependencias**:
   * Utilización de `pip-audit` en backend y `npm audit` en frontend dentro de la CI.
2. **Aislamiento de Secretos**:
   * Cero credenciales o claves de API harcodeadas en código fuente. Uso de `.env.example` como plantilla y GitHub Secrets para la configuración de entornos de CI/CD.
3. **Contenedores de Mínima Superficie**:
   * Ejecución como usuario `appuser` (non-root) en el backend y Nginx en Alpine para el frontend.
