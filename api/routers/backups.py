"""api/routers/backups.py — Configuration backup, verify, restore, download and upload."""

from __future__ import annotations

import asyncio
import re
import os
import secrets
import tarfile
import time
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from core.auth import auth_manager
from core.backup_jobs import BackupBusyError, backup_jobs
from core.settings import settings

router = APIRouter(prefix="/api/backups", tags=["Backups"])
manager = backup_jobs.manager

_UPLOAD_LIMIT = 20 * 1024 * 1024 * 1024
_UPLOAD_NAME_RE = re.compile(r"^amm-[A-Za-z0-9_-]+\.tar\.gz$")


class BackupCreate(BaseModel):
    label: Optional[str] = None


class RestoreRequest(BaseModel):
    sections: Optional[list[str]] = None


def _check_archive(path) -> None:
    with tarfile.open(path, "r:gz") as tar:
        if not any(member.isfile() for member in tar):
            raise tarfile.TarError("archive has no files")


def _ensure_authenticated(request: Request) -> None:
    if auth_manager.setup_required():
        # Recovery requires a secret supplied by the server operator, never a public bootstrap.
        expected = os.environ.get("AMM_BACKUP_RECOVERY_TOKEN", "")
        supplied = request.headers.get("X-AIO-Recovery-Token", "")
        allowed = request.method == "GET" and not request.url.path.endswith("/download")
        allowed = allowed or (request.method == "POST" and request.url.path.endswith(("/upload", "/restore", "/verify")))
        if len(expected) >= 32 and supplied and secrets.compare_digest(expected.encode(), supplied.encode()) and allowed:
            return
        raise HTTPException(status_code=401, detail="Administrator login or an operator recovery token is required.")
    auth_manager.authenticate_request(request)


def _not_found(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


def _busy(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.get("", summary="List configuration backups")
async def list_backups(request: Request) -> dict[str, Any]:
    _ensure_authenticated(request)
    return {
        "backup_dir": str(settings.backup_dir),
        "legacy_dir": str(manager.legacy_root),
        "retention": settings.backup_retention,
        "schedule": backup_jobs.public_status(),
        "job": backup_jobs.job_status(),
        "backups": manager.list_backups(),
    }


@router.get("/job", summary="Current or last backup job")
async def backup_job(request: Request) -> dict[str, Any]:
    _ensure_authenticated(request)
    return {"job": backup_jobs.job_status()}


@router.post("", status_code=status.HTTP_202_ACCEPTED, summary="Start a configuration backup")
async def create_backup(request: Request, body: Optional[BackupCreate] = None) -> dict[str, Any]:
    _ensure_authenticated(request)
    try:
        job = backup_jobs.start_backup((body.label if body else None) or "manual")
    except BackupBusyError as exc:
        raise _busy(exc) from exc
    return {"job": job}


@router.post("/upload", status_code=status.HTTP_201_CREATED, summary="Upload a backup archive")
async def upload_backup(request: Request, filename: str = "") -> dict[str, Any]:
    _ensure_authenticated(request)
    root = manager.backup_root
    root.mkdir(parents=True, exist_ok=True)
    name = filename if _UPLOAD_NAME_RE.match(filename or "") else f"amm-{time.strftime('%Y%m%d-%H%M%S')}-uploaded.tar.gz"
    target = root / name
    if target.exists():
        target = root / name.replace(".tar.gz", f"-{int(time.time())}.tar.gz")
    partial = target.with_name(target.name + ".partial")
    written = 0
    try:
        with partial.open("wb") as fh:
            async for chunk in request.stream():
                written += len(chunk)
                if written > _UPLOAD_LIMIT:
                    raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Upload too large.")
                fh.write(chunk)
        if not written:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty upload.")
        try:
            await asyncio.to_thread(_check_archive, partial)
        except (tarfile.TarError, OSError, EOFError) as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Not a valid .tar.gz backup: {exc}",
            ) from exc
        partial.replace(target)
    finally:
        partial.unlink(missing_ok=True)
    await asyncio.to_thread(manager.ensure_sidecar, target)
    item = next((row for row in manager.list_backups() if row["name"] == target.name), None)
    return {"status": "uploaded", "backup": item}


@router.get("/{name}", summary="Backup details")
async def backup_details(name: str, request: Request) -> dict[str, Any]:
    _ensure_authenticated(request)
    try:
        sections = await asyncio.to_thread(manager.backup_sections, name)
    except FileNotFoundError as exc:
        raise _not_found(exc) from exc
    item = next((row for row in manager.list_backups() if row["name"] == name), None)
    return {"backup": item, "sections": sections}


@router.get("/{name}/download", summary="Download a backup archive")
async def download_backup(name: str, request: Request) -> FileResponse:
    _ensure_authenticated(request)
    try:
        archive = manager.resolve_archive(name)
    except FileNotFoundError as exc:
        raise _not_found(exc) from exc
    return FileResponse(archive, media_type="application/gzip", filename=archive.name)


@router.post("/{name}/verify", status_code=status.HTTP_202_ACCEPTED, summary="Verify backup checksums")
async def verify_backup(name: str, request: Request) -> dict[str, Any]:
    _ensure_authenticated(request)
    try:
        return {"job": backup_jobs.start_verify(name)}
    except FileNotFoundError as exc:
        raise _not_found(exc) from exc
    except BackupBusyError as exc:
        raise _busy(exc) from exc


@router.post("/{name}/restore", status_code=status.HTTP_202_ACCEPTED, summary="Restore a configuration backup")
async def restore_backup(name: str, request: Request, body: Optional[RestoreRequest] = None) -> dict[str, Any]:
    _ensure_authenticated(request)
    try:
        return {"job": backup_jobs.start_restore(name, body.sections if body else None)}
    except FileNotFoundError as exc:
        raise _not_found(exc) from exc
    except BackupBusyError as exc:
        raise _busy(exc) from exc


@router.delete("/{name}", summary="Delete a configuration backup")
async def delete_backup(name: str, request: Request) -> dict[str, Any]:
    _ensure_authenticated(request)
    try:
        manager.delete_backup(name)
    except FileNotFoundError as exc:
        raise _not_found(exc) from exc
    return {"status": "deleted", "name": name}


class ExternalConfigBody(BaseModel):
    enabled: bool = False
    url: str = Field(default="", max_length=2048)
    username: str = Field(default="", max_length=200)
    password: str | None = Field(default=None, max_length=4096)
    encryption_password: str | None = Field(default=None, max_length=4096)


class ExternalActionBody(BaseModel):
    name: str = Field(min_length=1, max_length=255)


@router.get("/external/config", summary="External HTTPS/WebDAV backup settings")
async def external_config(request: Request):
    auth_manager.authenticate_request(request)
    from core.external_backups import ExternalBackups
    return ExternalBackups(settings).public()


@router.put("/external/config", summary="Configure encrypted external backups")
async def save_external_config(body: ExternalConfigBody, request: Request):
    auth_manager.authenticate_request(request)
    from core.external_backups import ExternalBackups
    if backup_jobs.busy:
        raise HTTPException(status_code=409, detail="Wait for the current backup operation to finish")
    try:
        return await asyncio.to_thread(ExternalBackups(settings).save, **body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/external/{action}", status_code=202, summary="Export, import or test a backup")
async def external_action(action: str, body: ExternalActionBody, request: Request):
    auth_manager.authenticate_request(request)
    try:
        return {"job": backup_jobs.start_external(action, body.name)}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except BackupBusyError as exc:
        raise _busy(exc) from exc
