"""Household homepage API — launcher and widgets, no process controls."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field

from core.auth import auth_manager
from core.debug_access import require_local_or_session
from core.homepage import (
    homepage_art,
    homepage_downloads,
    homepage_prowlarr_grab,
    homepage_recent,
    homepage_request,
    homepage_request_options,
    homepage_search,
    homepage_snapshot,
    homepage_trending,
)
from core.homepage_status import homepage_status
from core.integrations.seerr import sync_seerr_external_links

router = APIRouter(prefix="/api/homepage", tags=["Homepage"])


class HomepageRequestBody(BaseModel):
    mediaType: str = Field(min_length=2)
    mediaId: int
    seasons: Any | None = None
    serverId: int | None = None
    profileId: int | None = None
    rootFolder: str | None = None
    languageProfileId: int | None = None


class HomepageGrabBody(BaseModel):
    token: str = Field(min_length=8)


def _ensure_authenticated(request: Request) -> None:
    if not auth_manager.setup_required():
        auth_manager.authenticate_request(request)


@router.get("", summary="Household homepage snapshot")
async def get_homepage(request: Request, refresh: bool = False) -> dict[str, Any]:
    _ensure_authenticated(request)
    host = request.url.hostname or "127.0.0.1"
    scheme = request.url.scheme or "http"
    # Seerr's links to Radarr/Sonarr/Jellyfin need the address the browser uses; fire and forget.
    asyncio.get_running_loop().run_in_executor(None, sync_seerr_external_links, host)
    return await asyncio.to_thread(homepage_snapshot, host, force=refresh, scheme=scheme)


@router.get("/downloads", summary="Live download queues")
async def get_homepage_downloads(request: Request) -> dict[str, Any]:
    _ensure_authenticated(request)
    return await asyncio.to_thread(homepage_downloads)


@router.get("/status", summary="Now playing, storage, server and attention for Home")
async def get_homepage_status(request: Request) -> dict[str, Any]:
    # Host metrics: closed before setup like /api/system/info, unlike the rest of Home.
    require_local_or_session(request)
    host = request.url.hostname or "127.0.0.1"
    scheme = request.url.scheme or "http"
    return await asyncio.to_thread(homepage_status, host, scheme)


@router.get("/trending", summary="Another page of Seerr's trending titles")
async def get_homepage_trending(request: Request, page: int = Query(2, ge=1, le=500)) -> dict[str, Any]:
    _ensure_authenticated(request)
    host = request.url.hostname or "127.0.0.1"
    scheme = request.url.scheme or "http"
    return await asyncio.to_thread(homepage_trending, host, page, scheme)


@router.get("/recent", summary="Another page of Jellyfin's shows and movies, newest first")
async def get_homepage_recent(request: Request, page: int = Query(1, ge=1, le=500)) -> dict[str, Any]:
    _ensure_authenticated(request)
    host = request.url.hostname or "127.0.0.1"
    scheme = request.url.scheme or "http"
    return await asyncio.to_thread(homepage_recent, host, page, scheme)


@router.get("/art", summary="Poster image for Home rails")
async def homepage_artwork(request: Request, source: str = "", item_id: str = "") -> Response:
    _ensure_authenticated(request)
    body, content_type = await asyncio.to_thread(homepage_art, source, item_id)
    if not body:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artwork not found")
    return Response(content=body, media_type=content_type or "image/jpeg")


@router.get("/search", summary="Search Seerr or Prowlarr")
async def search_homepage(request: Request, q: str = "", provider: str = "seerr") -> dict[str, Any]:
    _ensure_authenticated(request)
    host = request.url.hostname or "127.0.0.1"
    return await asyncio.to_thread(homepage_search, host, q, provider)


@router.get("/request-options", summary="Folders and quality profiles for a Seerr request")
async def request_options(request: Request, mediaType: str = "movie") -> dict[str, Any]:
    _ensure_authenticated(request)
    return await asyncio.to_thread(homepage_request_options, mediaType)


@router.post("/request", summary="Submit a Seerr request")
async def request_media(request: Request, body: HomepageRequestBody) -> dict[str, Any]:
    _ensure_authenticated(request)
    result = await asyncio.to_thread(homepage_request, body.model_dump())
    if not result.get("ok"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.get("detail"))
    return result


@router.post("/grab", summary="Send a Prowlarr search result to a download client")
async def grab_release(request: Request, body: HomepageGrabBody) -> dict[str, Any]:
    _ensure_authenticated(request)
    result = await asyncio.to_thread(homepage_prowlarr_grab, body.token)
    if not result.get("ok"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.get("detail"))
    return result
