"""Router de la versión 1 de la API de LinkGuard."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.analyze import router as analyze_router

router = APIRouter()
router.include_router(analyze_router)

__all__ = ["router"]
