"""Household homepage API — launcher and widgets, no process controls."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from core.auth import auth_manager
from core.homepage import homepage_art, homepage_downloads, homepage_request, homepage_search, homepage_snapshot

router = APIRouter(prefix="/api/homepage", tags=["Homepage"])


class HomepageRequestBody(BaseModel):
    mediaType: str = Field(min_length=2)
    mediaId: int
    seasons: Any | None = None


def _ensure_authenticated(request: Request) -> None:
    if not auth_manager.setup_required():
        auth_manager.authenticate_request(request)


@router.get("", summary="Household homepage snapshot")
async def get_homepage(request: Request, refresh: bool = False) -> dict[str, Any]:
    _ensure_authenticated(request)
    host = request.url.hostname or "127.0.0.1"
    return await asyncio.to_thread(homepage_snapshot, host, force=refresh)


@router.get("/downloads", summary="Live download queues")
async def get_homepage_downloads(request: Request) -> dict[str, Any]:
    _ensure_authenticated(request)
    return await asyncio.to_thread(homepage_downloads)


@router.get("/art", summary="Poster image for Home rails")
async def homepage_artwork(request: Request, source: str = "", item_id: str = "") -> Response:
    _ensure_authenticated(request)
    body, content_type = await asyncio.to_thread(homepage_art, source, item_id)
    if not body:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artwork not found")
    return Response(content=body, media_type=content_type or "image/jpeg")


@router.get("/search", summary="Search library and Seerr")
async def search_homepage(request: Request, q: str = "") -> dict[str, Any]:
    _ensure_authenticated(request)
    host = request.url.hostname or "127.0.0.1"
    return await asyncio.to_thread(homepage_search, host, q)


@router.post("/request", summary="Submit a Seerr request")
async def request_media(request: Request, body: HomepageRequestBody) -> dict[str, Any]:
    _ensure_authenticated(request)
    result = await asyncio.to_thread(homepage_request, body.model_dump())
    if not result.get("ok"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.get("detail"))
    return result
