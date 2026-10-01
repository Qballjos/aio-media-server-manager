"""
api/routers/health.py — Health check endpoint.

GET /health  →  {"status": "ok", "version": "0.1.0"}
"""

from __future__ import annotations

from fastapi import APIRouter

from core.version import app_version, git_sha

router = APIRouter(tags=["Health"])


@router.get("/health", summary="Health check")
async def health() -> dict:
    """Returns service health status and application version."""
    payload = {"status": "ok", "version": app_version()}
    sha = git_sha()
    if sha:
        payload["git_sha"] = sha
    return payload
