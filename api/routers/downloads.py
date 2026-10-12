"""Pause or resume every download client from Home."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from core.auth import auth_manager
from core.downloads_pause import pause_all, resume_all

router = APIRouter(prefix="/api/downloads", tags=["Downloads"])


class PauseBody(BaseModel):
    minutes: int | None = Field(default=None, ge=1, le=24 * 60)  # empty pauses until resumed


def _ensure_authenticated(request: Request) -> None:
    if not auth_manager.setup_required():
        auth_manager.authenticate_request(request)


@router.post("/pause", summary="Pause SABnzbd, NZBGet and qBittorrent")
async def pause_downloads(body: PauseBody, request: Request) -> dict[str, Any]:
    _ensure_authenticated(request)
    return await asyncio.to_thread(pause_all, body.minutes)


@router.post("/resume", summary="Resume what Pause all paused")
async def resume_downloads(request: Request) -> dict[str, Any]:
    _ensure_authenticated(request)
    return await asyncio.to_thread(resume_all)
