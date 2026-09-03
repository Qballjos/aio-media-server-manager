"""
api/routers/system.py — System information endpoints.

GET /api/system/info  →  resolved paths, puid/pgid, storage validation,
                          supervisor process list.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from core.settings import settings
from core.storage import StorageManager
from core.supervisor import ProcessSupervisor

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/system", tags=["System"])


@router.get("/info", summary="System information")
async def system_info() -> dict:
    """
    Returns:
    - Resolved storage paths
    - PUID / PGID
    - Per-path validation results (exists, writable, filesystem type)
    - Supervisor process list
    """
    sm = StorageManager(settings)
    path_info = sm.validate_all()

    paths_summary = {}
    for label, info in path_info.items():
        paths_summary[label] = {
            "path": str(info.path),
            "exists": info.exists,
            "is_dir": info.is_dir,
            "writable": info.writable,
            "fs_type": info.fs_type,
            "is_network_fs": info.is_network_fs,
            "is_fuse_fs": info.is_fuse_fs,
            "hardlinks_supported": info.hardlinks_supported,
        }

    supervisor = ProcessSupervisor.get()
    processes = supervisor.list_processes()

    return {
        "settings": settings.as_serialisable_dict(),
        "storage": paths_summary,
        "processes": processes,
    }


@router.get("/processes", summary="List supervised processes")
async def list_processes() -> dict:
    """Returns the current state of all supervised processes."""
    supervisor = ProcessSupervisor.get()
    return {"processes": supervisor.list_processes()}


@router.get("/processes/{name}/logs", summary="Get process logs")
async def get_process_logs(name: str) -> dict:
    """Returns the last 500 log lines for a named process."""
    supervisor = ProcessSupervisor.get()
    logs = supervisor.get_logs(name)
    if not logs and name not in {p["name"] for p in supervisor.list_processes()}:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Process '{name}' not found.")
    return {"name": name, "logs": logs}
