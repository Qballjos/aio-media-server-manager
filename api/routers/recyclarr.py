"""Recyclarr TRaSH config editor and sync."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from core.auth import auth_manager
from core.recyclarr import apply_prefs_and_render, config_payload, run_sync, save_yaml

router = APIRouter(prefix="/api/recyclarr", tags=["Recyclarr"])


class RecyclarrPrefsBody(BaseModel):
    sonarr_web_1080p: bool | None = None
    sonarr_web_2160p: bool | None = None
    sonarr_anime: bool | None = None
    radarr_hd: bool | None = None
    radarr_uhd: bool | None = None
    naming: str | None = None


class RecyclarrYamlBody(BaseModel):
    yaml: str = Field(min_length=1)


def _ensure_authenticated(request: Request) -> None:
    if not auth_manager.setup_required():
        auth_manager.authenticate_request(request)


@router.get("", summary="Read Recyclarr YAML and TRaSH profile flags")
async def get_recyclarr(request: Request) -> dict[str, Any]:
    _ensure_authenticated(request)
    return config_payload()


@router.put("", summary="Replace Recyclarr YAML")
async def put_recyclarr_yaml(request: Request, body: RecyclarrYamlBody) -> dict[str, Any]:
    _ensure_authenticated(request)
    payload = config_payload()
    save_yaml(payload["config_dir"], body.yaml)
    return config_payload()


@router.patch("", summary="Update TRaSH profile flags and regenerate YAML")
async def patch_recyclarr_prefs(request: Request, body: RecyclarrPrefsBody) -> dict[str, Any]:
    _ensure_authenticated(request)
    current = config_payload()["prefs"]
    updates = {key: value for key, value in body.model_dump().items() if value is not None}
    return apply_prefs_and_render({**current, **updates}, force=True)


@router.post("/reset", summary="Restore TRaSH default Recyclarr YAML")
async def reset_recyclarr(request: Request) -> dict[str, Any]:
    _ensure_authenticated(request)
    return apply_prefs_and_render({}, force=True)


@router.post("/sync", summary="Run recyclarr sync once")
async def sync_recyclarr(request: Request) -> dict[str, Any]:
    _ensure_authenticated(request)
    result = run_sync()
    if not result.get("ok"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.get("detail"))
    return result
