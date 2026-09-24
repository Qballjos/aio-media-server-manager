"""Catalog update check/apply status and manual triggers."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core.auth import auth_manager
from core.installer.github import GitHubRateLimitError
from core.update_schedule import scheduler

router = APIRouter(prefix="/api/updates", tags=["Updates"])


def _ensure_authenticated(request: Request) -> None:
    if auth_manager.setup_required():
        raise HTTPException(status_code=400, detail="Setup required.")
    auth_manager.authenticate_request(request)


class UpdateRunBody(BaseModel):
    apply: bool = False
    names: Optional[list[str]] = None


@router.get("/status", summary="Scheduled update status and available versions")
async def updates_status(request: Request) -> dict[str, Any]:
    _ensure_authenticated(request)
    return scheduler.public_status()


@router.post("/check", summary="Run an update check now")
async def updates_check(request: Request) -> dict[str, Any]:
    _ensure_authenticated(request)
    try:
        return await scheduler.tick(force_check=True, force_apply=False)
    except GitHubRateLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc


@router.post("/apply", summary="Apply cached catalog updates")
async def updates_apply(body: UpdateRunBody, request: Request) -> dict[str, Any]:
    _ensure_authenticated(request)
    from core.maintenance import pause_reason

    paused = pause_reason()
    if paused:
        raise HTTPException(status_code=409, detail=f"Updates paused ({paused}).")
    return await scheduler.apply_available(body.names)
