"""
api/routers/system.py — System information endpoints.

GET /api/system/info  →  operational status (incl. host metrics) for a session;
                          full dump from localhost or while Diagnostics support share is on.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Request

import psutil

from core.cloudflare_tunnel import cloudflare_tunnel
from core.debug_access import can_view_debug, is_local_troubleshooting, require_local_or_debug_switch, require_local_or_session
from core.library_layout import LibraryLayout
from core.log_redactor import redact_log_line
from core.metrics import collect_metrics
from core.settings import settings
from core.storage import StorageManager
from core.supervisor import ProcessSupervisor
from core.transcoding import probe_transcoding
from core.vpn import vpn_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/system", tags=["System"])


def _operational_status() -> dict:
    # Omit debug:false — older Host health UIs treated that as a permanent
    # "turn on Support share" banner even though metrics are already included.
    return {
        "transcoding": probe_transcoding(),
        "vpn": vpn_manager.status(),
        "cloudflare_tunnel": cloudflare_tunnel.status(),
        # Safe for any logged-in admin session (Host health / Settings overview).
        "metrics": collect_metrics(),
    }


def _debug_status() -> dict:
    sm = StorageManager(settings)
    path_info = sm.validate_all()
    paths_summary = {}
    for label, info in path_info.items():
        entry = {
            "path": str(info.path),
            "exists": info.exists,
            "is_dir": info.is_dir,
            "writable": info.writable,
            "fs_type": info.fs_type,
            "is_network_fs": info.is_network_fs,
            "is_fuse_fs": info.is_fuse_fs,
            "hardlinks_supported": info.hardlinks_supported,
        }
        try:
            usage = psutil.disk_usage(str(info.path) if info.exists else "/")
            entry["disk_total"] = usage.total
            entry["disk_used"] = usage.used
            entry["disk_percent"] = usage.percent
        except Exception:
            entry["disk_total"] = 0
            entry["disk_used"] = 0
            entry["disk_percent"] = 0
        paths_summary[label] = entry

    supervisor = ProcessSupervisor.get()
    payload = _operational_status()
    payload.update(
        {
            "debug": True,
            "settings": settings.as_serialisable_dict(),
            "storage": paths_summary,
            "processes": supervisor.list_processes(),
            "metrics": collect_metrics(),
            "library": LibraryLayout.from_settings(settings).as_dict(),
        }
    )
    return payload


@router.get("/info", summary="System information")
async def system_info(request: Request) -> dict:
    """
    Session: VPN, transcoding, Cloudflare, and host metrics. Full host dump from
    localhost, or from a session while Diagnostics → Support share is on.
    """
    if can_view_debug(request):
        return await asyncio.to_thread(_debug_status)
    require_local_or_session(request)
    return await asyncio.to_thread(_operational_status)


@router.get("/processes", summary="List supervised processes")
async def list_processes(request: Request) -> dict:
    """Supervisor process list — localhost or Diagnostics support share."""
    require_local_or_debug_switch(request)
    supervisor = ProcessSupervisor.get()
    return {"processes": supervisor.list_processes()}


@router.get("/processes/{name}/logs", summary="Get process logs")
async def get_process_logs(name: str, request: Request) -> dict:
    """Process logs — localhost (raw) or Diagnostics support share (redacted)."""
    require_local_or_debug_switch(request)
    supervisor = ProcessSupervisor.get()
    logs = supervisor.get_logs(name)
    if not logs and name not in {p["name"] for p in supervisor.list_processes()}:
        raise HTTPException(status_code=404, detail=f"Process '{name}' not found.")
    if not is_local_troubleshooting(request):
        logs = [redact_log_line(line) for line in logs]
    return {"name": name, "logs": logs}
