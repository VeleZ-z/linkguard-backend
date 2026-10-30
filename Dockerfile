# syntax=docker/dockerfile:1
# ---------------------------------------------------------------------------
# LinkGuard Backend — imagen multi-stage (H1-T11)
#
# Etapa 1 (builder): instala las dependencias de producción en /opt/venv.
# Etapa 2 (runner): copia solo el venv y el código de app/, ejecuta como
# usuario no privilegiado (UID 10001) y declara un HEALTHCHECK a /health.
# El servicio es stateless: no se persiste nada en disco (RNF-103).
# ---------------------------------------------------------------------------

# STAGE 1: Builder (instalación de dependencias)
FROM python:3.12-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# gcc solo es necesario si alguna dependencia debe compilarse; no pasa al runner.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
# --no-compile evita __pycache__ y pip/setuptools se retiran del venv final.
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir --no-compile -r requirements.txt \
    && pip uninstall -y pip setuptools wheel \
    && find /opt/venv -type d -name "__pycache__" -prune -exec rm -rf {} +

# STAGE 2: Runtime (imagen final liviana y sin privilegios)
FROM python:3.12-slim AS runner

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    PORT=8000

WORKDIR /app

# Usuario de sistema sin privilegios (sin shell de login ni home escribible).
RUN groupadd -g 10001 appgroup \
    && useradd -u 10001 -g appgroup -M -s /usr/sbin/nologin appuser

COPY --from=builder /opt/venv /opt/venv

# La imagen base trae su propio pip/ensurepip dentro del intérprete del sistema;
# el servicio no los necesita en tiempo de ejecución.
RUN rm -rf /usr/local/lib/python3.12/site-packages/pip* \
    /usr/local/lib/python3.12/site-packages/setuptools* \
    /usr/local/lib/python3.12/ensurepip \
    /usr/local/lib/python3.12/site-packages/__pycache__

COPY --chown=appuser:appgroup ./app /app/app

# Sin escrituras: el usuario no es dueño de /app (solo lectura del código).
USER appuser

EXPOSE 8000

# El HEALTHCHECK consulta el mismo puerto en el que escucha Uvicorn: Render
# inyecta PORT=10000, así que un puerto fijo dejaría el contenedor en bucle de
# reinicio. Se resuelve en Python para no depender de la expansión del shell.
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://localhost:' + os.environ.get('PORT', '8000') + '/health', timeout=4)" || exit 1

# OBS-3: `--proxy-headers` hace que Uvicorn reescriba `scope["client"]` con la
# IP de `X-Forwarded-For`, de modo que el rate limit (30/min) se aplica por
# cliente real y no por la IP del proxy de Render. `--forwarded-allow-ips='*'`
# es necesario porque el proxy de la plataforma no tiene una IP fija: el
# servicio no está expuesto directamente a Internet, solo a través del edge.
# `${PORT:-8000}` permite que Render inyecte su puerto sin reconstruir la
# imagen, manteniendo 8000 como valor local por defecto.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
