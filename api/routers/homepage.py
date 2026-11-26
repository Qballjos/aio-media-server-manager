"""Household homepage API — launcher and widgets, no process controls."""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Path, Query, Request, Response, status
from pydantic import BaseModel, Field

from api.routers.media_users import _client as _seerr_client
from core.auth import auth_manager
from core.integrations.streaming import ADMIN_STREAMING_ACCOUNT, streaming_availability
from core.tv_devices import is_tv_request
from core.debug_access import require_local_or_session
from core.homepage import (
    clear_homepage_snapshot_cache,
    homepage_art,
    homepage_calendar,
    homepage_downloads,
    homepage_prowlarr_grab,
    homepage_recent,
    homepage_resume,
    homepage_request,
    homepage_request_options,
    homepage_search,
    homepage_snapshot,
    homepage_title,
    homepage_trending,
)
from core.homepage_other import homepage_other_downloads
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
async def get_homepage(request: Request, refresh: bool = False, include_calendar: bool = True) -> dict[str, Any]:
    _ensure_authenticated(request)
    host = request.url.hostname or "127.0.0.1"
    scheme = request.url.scheme or "http"
    # Seerr's links to Radarr/Sonarr/Jellyfin need the address the browser uses; fire and forget.
    if not is_tv_request(request):
        asyncio.get_running_loop().run_in_executor(None, sync_seerr_external_links, host)
    return await asyncio.to_thread(homepage_snapshot, host, force=refresh, scheme=scheme, include_calendar=include_calendar)


@router.get("/calendar", summary="Admin calendar date range")
async def get_homepage_calendar(
    request: Request, response: Response, start: date, days: Annotated[int, Query(ge=1, le=42)] = 7,
) -> dict[str, Any]:
    auth_manager.authenticate_request(request)
    end = start + timedelta(days=min(days - 1, (date.max - start).days))
    response.headers["Cache-Control"] = "private, no-store"
    return await asyncio.to_thread(
        homepage_calendar, request.url.hostname or "127.0.0.1", request.url.scheme, start, end,
    )


@router.get("/downloads", summary="Live download queues")
async def get_homepage_downloads(request: Request) -> dict[str, Any]:
    _ensure_authenticated(request)
    return await asyncio.to_thread(homepage_downloads)


@router.get("/resume", summary="Continue watching without exporting Jellyfin credentials")
async def get_homepage_resume(request: Request) -> dict[str, Any]:
    auth_manager.authenticate_request(request)
    return await asyncio.to_thread(homepage_resume)


@router.get("/other-downloads", summary="Downloads that are not films or series")
async def get_homepage_other_downloads(request: Request) -> dict[str, Any]:
    _ensure_authenticated(request)
    return await asyncio.to_thread(homepage_other_downloads)


@router.get("/status", summary="Now playing, storage, server and attention for Home")
async def get_homepage_status(request: Request) -> dict[str, Any]:
    # Host metrics: closed before setup like /api/system/info, unlike the rest of Home.
    require_local_or_session(request)
    host = request.url.hostname or "127.0.0.1"
    scheme = request.url.scheme or "http"
    return await asyncio.to_thread(homepage_status, host, scheme)


@router.get("/title", summary="Overview, ratings and trailer for one Seerr title")
async def get_homepage_title(
    request: Request,
    response: Response,
    mediaType: str = "",
    mediaId: int = Query(0, ge=0),
) -> dict[str, Any]:
    _ensure_authenticated(request)
    host = request.url.hostname or "127.0.0.1"
    scheme = request.url.scheme or "http"
    result = await asyncio.to_thread(homepage_title, host, scheme, mediaType, mediaId)
    if not result.get("ok"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.get("detail"))
    providers = result.pop("watchProviders", None)
    if not auth_manager.setup_required():
        preference = await asyncio.to_thread(auth_manager.media_users.streaming, ADMIN_STREAMING_ACCOUNT)
        result["streaming"] = streaming_availability(providers, preference)
        response.headers["Cache-Control"] = "private, no-store"
    return result


@router.get("/trending", summary="Another page of Seerr's trending titles")
async def get_homepage_trending(request: Request, page: int = Query(2, ge=1, le=500)) -> dict[str, Any]:
    _ensure_authenticated(request)
    host = request.url.hostname or "127.0.0.1"
    scheme = request.url.scheme or "http"
    return await asyncio.to_thread(homepage_trending, host, page, scheme)


@router.get("/recent", summary="Another page of Jellyfin's shows and movies, newest first")
async def get_homepage_recent(
    request: Request,
    page: int = Query(1, ge=1, le=500),
    mediaType: Literal["", "movie", "tv"] = "",
) -> dict[str, Any]:
    _ensure_authenticated(request)
    host = request.url.hostname or "127.0.0.1"
    scheme = request.url.scheme or "http"
    return await asyncio.to_thread(homepage_recent, host, page, scheme, mediaType)


@router.get("/art", summary="Poster or backdrop image for Home rails")
async def homepage_artwork(
    request: Request,
    source: str = "",
    item_id: str = "",
    image: Literal["Primary", "Backdrop", "Thumb"] = "Primary",
    fillWidth: int = Query(240, ge=1, le=3840),
    fillHeight: int = Query(360, ge=1, le=2160),
) -> Response:
    _ensure_authenticated(request)
    body, content_type = await asyncio.to_thread(homepage_art, source, item_id, image, fillWidth, fillHeight)
    if not body:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artwork not found")
    return Response(content=body, media_type=content_type or "image/jpeg")


@router.get("/search", summary="Search Seerr or Prowlarr")
async def search_homepage(request: Request, q: str = "", provider: str = "seerr") -> dict[str, Any]:
    _ensure_authenticated(request)
    host = request.url.hostname or "127.0.0.1"
    return await asyncio.to_thread(homepage_search, host, q, provider)


def _request_options(media_type: str, media_id: int | None) -> dict[str, Any]:
    options = homepage_request_options(media_type)
    if options.get("ok", True) and media_type == "tv" and media_id is not None:
        options["seasons"] = _request_options_for_series(media_id)
    return options


def _request_options_for_series(media_id: int) -> list[int]:
    with _seerr_client() as seerr:
        return seerr.admin_requestable_seasons(media_id)


@router.get("/request-options", summary="Seasons, folders and quality profiles for a Seerr request")
async def request_options(
    request: Request, response: Response, mediaType: str = "movie", mediaId: int | None = Query(None, gt=0),
) -> dict[str, Any]:
    auth_manager.authenticate_request(request)
    response.headers["Cache-Control"] = "private, no-store"
    return await asyncio.to_thread(_request_options, mediaType, mediaId)


@router.post("/request", summary="Submit a Seerr request")
async def request_media(request: Request, body: HomepageRequestBody) -> dict[str, Any]:
    _ensure_authenticated(request)
    payload = body.model_dump()
    if is_tv_request(request):
        payload = {key: payload[key] for key in ("mediaType", "mediaId", "seasons")}
    elif body.mediaType == "tv" and isinstance(body.seasons, list):
        if not body.seasons or len(body.seasons) > 100 or any(type(season) is not int or season < 0 for season in body.seasons):
            raise HTTPException(422, "Select valid seasons for a series request.")
        options = await asyncio.to_thread(_request_options_for_series, body.mediaId)
        if not set(body.seasons).issubset(options):
            raise HTTPException(409, {"message": "Some seasons can no longer be requested.", "seasons": options})
        payload["seasons"] = sorted(set(body.seasons))
    result = await asyncio.to_thread(homepage_request, payload)
    if not result.get("ok"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.get("detail"))
    return result


@router.post("/requests/{request_id}/{action}")
def review_media_request(
    request: Request, request_id: Annotated[int, Path(gt=0)], action: Literal["approve", "decline"],
):
    auth_manager.authenticate_request(request)
    with _seerr_client() as client:
        client.review_request(request_id, action)
    clear_homepage_snapshot_cache()
    return {"ok": True}


@router.post("/grab", summary="Send a Prowlarr search result to a download client")
async def grab_release(request: Request, body: HomepageGrabBody) -> dict[str, Any]:
    _ensure_authenticated(request)
    result = await asyncio.to_thread(homepage_prowlarr_grab, body.token)
    if not result.get("ok"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.get("detail"))
    return result
