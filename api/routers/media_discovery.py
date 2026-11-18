"""Catalog-only discovery and the shared Trending preference."""

from concurrent.futures import ThreadPoolExecutor
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Path, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator

from api.routers.media_users import _client as _seerr_client
from applications.catalog import ApplicationCatalog
from core.auth import auth_manager
from core.file_io import write_private_text
from core.integrations.member_library import member_availability, poster_for_member, recent_for_member
from core.homepage import _seerr_search, homepage_trending, seerr_catalog_details

router = APIRouter(prefix="/api/media-discovery", tags=["Media discovery"])
TrendingFilter = Literal["all", "movie", "tv"]
_CATALOG_FIELDS = ("mediaType", "mediaId", "title", "year", "detail", "poster", "overview")


class TrendingPreference(BaseModel):
    filter: TrendingFilter


def _filter_path():
    return auth_manager.media_users.path.with_name("trending-filter")


def _read_filter() -> TrendingFilter:
    try:
        value = _filter_path().read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return "all"
    return value if value in ("movie", "tv") else "all"


def _catalog_items(rows: list[dict]) -> list[dict]:
    return [{key: row[key] for key in _CATALOG_FIELDS if key in row} for row in rows]


def _mark_availability(request: Request, rows: list[dict], *, own_requests: bool = False) -> None:
    titles = {
        (row["mediaType"], row["mediaId"]): row["title"] for row in rows
        if row.get("mediaType") in ("movie", "tv") and type(row.get("mediaId")) is int and row.get("title")
    }
    available = {}
    if titles:
        try:
            token = auth_manager.member_library_token(request)
        except HTTPException as exc:
            if exc.status_code != 409:
                raise
        else:
            available = member_availability(*request.state.media_account, token, titles)
    for row in rows:
        key = (row.get("mediaType"), row.get("mediaId"))
        seasons = available.get(key)
        if seasons is not None:
            if key[0] == "movie":
                row["available"] = True
            elif own_requests:
                requested = set(row["seasons"])
                row["availableSeasons"] = sorted(requested & seasons)
                if requested and requested <= seasons:
                    row["available"] = True
            else:
                row["availableSeasons"] = sorted(seasons)
        if own_requests:
            row.pop("mediaId", None)


@router.get("/trending-filter")
def get_trending_filter(request: Request, response: Response):
    auth_manager.authenticate_request(request)
    response.headers["Cache-Control"] = "no-store"
    return {"filter": _read_filter()}


@router.put("/trending-filter")
def set_trending_filter(body: TrendingPreference, request: Request):
    auth_manager.authenticate_request(request)
    write_private_text(_filter_path(), body.filter + "\n")
    return body


@router.get("/search")
def search_catalog(request: Request, response: Response, q: Annotated[str, Query(max_length=160)]):
    auth_manager.authenticate_member_request(request)
    response.headers["Cache-Control"] = "no-store"
    term = q.strip()
    if len(term) < 2:
        return {"items": []}
    rows, error = _seerr_search(ApplicationCatalog(), term)
    if error:
        raise HTTPException(502, "Media search is temporarily unavailable.")
    items = _catalog_items(rows)
    _mark_availability(request, items)
    return {"items": items}


@router.get("/trending")
def trending_catalog(request: Request, response: Response, page: Annotated[int, Query(ge=1, le=100)] = 1):
    auth_manager.authenticate_member_request(request)
    response.headers["Cache-Control"] = "no-store"
    selected = _read_filter()
    result = homepage_trending("127.0.0.1", page)
    if result.get("error"):
        raise HTTPException(502, "Trending is temporarily unavailable.")
    rows = result["items"]
    items = _catalog_items([row for row in rows if selected in ("all", row["mediaType"])])
    _mark_availability(request, items)
    return {
        "items": items,
        "has_more": bool(rows) and page < 100,
    }


@router.get("/requests")
def member_requests(request: Request, response: Response, page: Annotated[int, Query(ge=1)] = 1):
    auth_manager.authenticate_member_request(request)
    take = 20
    skip = (page - 1) * take
    with _seerr_client() as client:
        user_id = client.member_user_id(*request.state.media_account)
        payload = client.user_requests(user_id, take, skip)
        base_url, api_key = client.base_url, client.api_key
    rows = payload["results"]
    statuses = {1: "pending", 2: "approved", 3: "declined"}
    requests = []
    for row in rows:
        owner = row.get("requestedBy") or {}
        media = row.get("media") or {}
        kind = row.get("type") or media.get("mediaType")
        media_id = media.get("tmdbId")
        if owner.get("id") == user_id and kind in ("movie", "tv") and type(media_id) is int and media_id > 0:
            requests.append((row, kind, media_id))

    headers = {"X-Api-Key": api_key or ""}

    def card(entry):
        row, kind, media_id = entry
        details = seerr_catalog_details(base_url, headers, kind, media_id)
        return {
            "id": row["id"],
            "status": statuses.get(row.get("status"), "unknown"),
            "title": details.get("title") or "",
            "poster": details.get("poster") or "",
            "mediaType": kind,
            "mediaId": media_id,
            "createdAt": row.get("createdAt"),
            "seasons": sorted({
                season["seasonNumber"] for season in (row.get("seasons") or [])
                if isinstance(season, dict) and type(season.get("seasonNumber")) is int and season["seasonNumber"] >= 0
            }),
        }

    with ThreadPoolExecutor(max_workers=6) as pool:
        items = list(pool.map(card, requests))
    _mark_availability(request, items, own_requests=True)
    response.headers["Cache-Control"] = "no-store"
    return {"items": items, "has_more": skip + len(rows) < payload["pageInfo"]["results"]}


@router.get("/quota")
def member_quota(request: Request, response: Response):
    auth_manager.authenticate_member_request(request)
    with _seerr_client() as client:
        user_id = client.member_user_id(*request.state.media_account)
        quota = client.user_quota(user_id)

    result = {}
    for kind in ("movie", "tv"):
        row = quota.get(kind) if isinstance(quota, dict) else None
        if not isinstance(row, dict):
            raise HTTPException(502, "Seerr did not return the request limits.")
        limit = row.get("limit")
        if limit is None or limit == 0:
            result[kind] = None
            continue
        remaining, days = row.get("remaining"), row.get("days")
        if any(type(value) is not int or value < 0 for value in (limit, remaining, days)):
            raise HTTPException(502, "Seerr returned invalid request limits.")
        result[kind] = {"limit": limit, "remaining": remaining, "days": days}
    response.headers["Cache-Control"] = "no-store"
    return result


class MemberRequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mediaType: Literal["movie", "tv"]
    mediaId: int = Field(gt=0, strict=True)
    seasons: list[Annotated[int, Field(ge=0, strict=True)]] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_seasons(self):
        if bool(self.seasons) != (self.mediaType == "tv"):
            raise ValueError("Select seasons for a series request.")
        return self


@router.get("/tv/{media_id}/seasons")
def get_request_seasons(request: Request, response: Response, media_id: Annotated[int, Path(gt=0)]):
    auth_manager.authenticate_member_request(request)
    with _seerr_client() as client:
        seasons = client.request_seasons(media_id)
    response.headers["Cache-Control"] = "no-store"
    return {"seasons": seasons}


@router.post("/requests", status_code=201)
def submit_member_request(body: MemberRequestBody, request: Request):
    auth_manager.authenticate_member_request(request)
    payload: dict = {"mediaType": body.mediaType, "mediaId": body.mediaId}
    if body.seasons:
        payload["seasons"] = sorted(set(body.seasons))
    with _seerr_client() as client:
        user_id = client.member_user_id(*request.state.media_account)
        request_id = client.submit_member_request(user_id, payload)
    return {"id": request_id}


@router.get("/recent")
def member_recent(request: Request, response: Response):
    token = auth_manager.member_library_token(request)
    items = recent_for_member(*request.state.media_account, token)
    response.headers["Cache-Control"] = "no-store"
    return {"items": items}


@router.get("/recent/art/{item_id}")
def member_recent_art(request: Request, item_id: Annotated[str, Path(max_length=36)]):
    token = auth_manager.member_library_token(request)
    body, media_type = poster_for_member(*request.state.media_account, token, item_id)
    return Response(body, media_type=media_type, headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})
