"""api/routers/backups.py — Configuration backup and restore endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, status

from core.auth import auth_manager
from core.backup_manager import BackupManager
from core.settings import settings

router = APIRouter(prefix="/api/backups", tags=["Backups"])
manager = BackupManager(settings)


def _ensure_authenticated(request: Request) -> None:
    if not auth_manager.setup_required():
        auth_manager.authenticate_request(request)


@router.get("", summary="List configuration backups")
async def list_backups(request: Request) -> dict[str, Any]:
    _ensure_authenticated(request)
    return {
        "backup_dir": str(settings.backup_dir),
        "retention": settings.backup_retention,
        "backups": manager.list_backups(),
    }


@router.post("", summary="Create a configuration backup")
async def create_backup(request: Request) -> dict[str, Any]:
    _ensure_authenticated(request)
    body = {}
    try:
        body = await request.json()
    except Exception:
        body = {}
    label = body.get("label") if isinstance(body, dict) else None
    return manager.create_backup(label=label)


@router.post("/{name}/restore", summary="Restore a configuration backup")
async def restore_backup(name: str, request: Request) -> dict[str, Any]:
    _ensure_authenticated(request)
    try:
        return manager.restore_backup(name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
