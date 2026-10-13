"""Pause or resume every download client from Home."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from core.auth import auth_manager
from core.download_cleanup import remove_downloads
from core.downloads_pause import pause_all, resume_all

router = APIRouter(prefix="/api/downloads", tags=["Downloads"])


class RemoveItem(BaseModel):
    source: str = Field(pattern="^(sabnzbd|nzbget|qbittorrent)$")
    download_id: str = Field(min_length=1, max_length=200)


class RemoveBody(BaseModel):
    items: list[RemoveItem] = Field(min_length=1, max_length=200)


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


@router.post("/remove", summary="Remove stuck downloads; Sonarr/Radarr blocklist them and search again")
async def remove_stuck_downloads(body: RemoveBody, request: Request) -> dict[str, Any]:
    _ensure_authenticated(request)
    return await asyncio.to_thread(remove_downloads, [item.model_dump() for item in body.items])
