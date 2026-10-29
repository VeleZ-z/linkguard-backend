"""Aplicación FastAPI de LinkGuard (H1-T08 y H1-T10).

Expone ``GET /health`` y monta el router v1 bajo ``/api/v1``. Configura CORS
restringido, rate limiting por IP y manejadores de error que nunca filtran
trazas internas al cliente.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from app.api.v1.router import router as api_router
from app.core.config import get_settings
from app.core.errors import LinkGuardError, URLTooLongError
from app.core.logging import configure_logging, get_logger
from app.core.rate_limit import limiter

#: Identidad publicada por el endpoint de salud y el contrato.
SERVICE_NAME: str = "linkguard-api"
SERVICE_VERSION: str = "1.0.0"

settings = get_settings()
configure_logging()
logger = get_logger()

app = FastAPI(
    title="LinkGuard API",
    version=SERVICE_VERSION,
    description=(
        "Servicio de evaluación sintáctico-léxica del riesgo de phishing en "
        "URLs. Análisis local sin conexiones al enlace evaluado (RNF-101)."
    ),
)

#: slowapi exige exponer el limitador en el estado de la aplicación.
app.state.limiter = limiter

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Accept"],
)


@app.exception_handler(RateLimitExceeded)
async def _rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Devuelve HTTP 429 con un mensaje en es-419 al exceder el límite."""
    return JSONResponse(
        status_code=429,
        content={
            "error": {
                "code": "rate_limit_exceeded",
                "message": "Ha superado el límite de solicitudes permitidas por minuto",
            }
        },
    )


@app.exception_handler(LinkGuardError)
async def _linkguard_error_handler(request: Request, exc: LinkGuardError) -> JSONResponse:
    """Mapea los errores de dominio al sobre ``{"error": {...}}`` con HTTP 400."""
    return JSONResponse(status_code=exc.status_code, content=exc.to_dict())


@app.exception_handler(RequestValidationError)
async def _validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Mantiene 422 para el contrato, pero eleva el exceso de longitud a 400.

    ``AnalyzeRequest`` limita ``url`` a 4096 caracteres, por lo que una entrada
    más larga nunca llega al normalizador. El contrato exige responder 400 con
    el mensaje de ``URLTooLongError`` en ese caso (RF-105).
    """
    for error in exc.errors():
        location = tuple(error.get("loc", ()))
        if location[-1:] == ("url",) and error.get("type") == "string_too_long":
            return JSONResponse(status_code=400, content=URLTooLongError().to_dict())
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_error",
                "message": "La solicitud no cumple el contrato de la API",
            }
        },
    )


@app.exception_handler(Exception)
async def _unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Responde 500 estandarizado sin filtrar trazas ni detalles internos."""
    logger.exception("Error no controlado durante la solicitud")
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_error",
                "message": "Ocurrió un error interno. Intente nuevamente más tarde.",
            }
        },
    )


@app.get("/health", tags=["health"], summary="Estado de salud del servicio")
async def health() -> dict[str, str]:
    """Responde 200 con la identidad y la marca temporal del servicio."""
    return {
        "status": "healthy",
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION,
        "timestamp": datetime.now(UTC).isoformat(),
    }


app.include_router(api_router, prefix="/api/v1")

__all__ = ["SERVICE_NAME", "SERVICE_VERSION", "app"]
