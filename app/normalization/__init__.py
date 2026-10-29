"""Capa de normalización sintáctica de URLs (Módulo 100)."""

from __future__ import annotations

from app.normalization.normalizer import ALLOWED_SCHEMES, MAX_URL_LENGTH, normalize

__all__ = ["ALLOWED_SCHEMES", "MAX_URL_LENGTH", "normalize"]
