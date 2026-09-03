"""
api/routers/health.py — Health check endpoint.

GET /health  →  {"status": "ok", "version": "0.1.0"}
"""

from __future__ import annotations

import importlib.metadata

from fastapi import APIRouter

router = APIRouter(tags=["Health"])


def _get_version() -> str:
    try:
        return importlib.metadata.version("aio-media-manager")
    except importlib.metadata.PackageNotFoundError:
        return "0.1.0-dev"


@router.get("/health", summary="Health check")
async def health() -> dict:
    """Returns service health status and application version."""
    return {"status": "ok", "version": _get_version()}
