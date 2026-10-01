"""VPN status and control for torrent traffic only."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Request

from core.auth import auth_manager
from core.vpn import vpn_manager

router = APIRouter(prefix="/api/vpn", tags=["VPN"])


def _ensure_authenticated(request: Request) -> None:
    if not auth_manager.setup_required():
        auth_manager.authenticate_request(request)


def _persist_vpn_policy(*, enabled: bool) -> None:
    from core.settings import settings

    settings.vpn_enabled = enabled
    settings.vpn_enforce = enabled
    try:
        settings.save()
    except Exception:
        pass


@router.get("/status")
async def vpn_status(request: Request) -> dict[str, Any]:
    _ensure_authenticated(request)
    return await asyncio.to_thread(vpn_manager.status)


@router.post("/start")
async def vpn_start(request: Request) -> dict[str, Any]:
    """Enable VPN policy and bring the tunnel up."""
    _ensure_authenticated(request)
    from core.integrations.lifecycle import enforce_vpn_isolation, start_tunneled_apps, stop_tunneled_apps

    _persist_vpn_policy(enabled=True)
    stopped = await stop_tunneled_apps()
    result = await asyncio.to_thread(vpn_manager.start)
    if result.get("tunnel_up"):
        result["started_apps"] = await start_tunneled_apps(stopped)
    else:
        await enforce_vpn_isolation()
        result["started_apps"] = []
    return result


@router.post("/stop")
async def vpn_stop(request: Request) -> dict[str, Any]:
    """Bring the tunnel down. Kill switch stays on while VPN remains enabled."""
    _ensure_authenticated(request)
    from core.integrations.lifecycle import enforce_vpn_isolation, start_tunneled_apps, stop_tunneled_apps
    from core.settings import settings

    stopped = await stop_tunneled_apps()
    result = await asyncio.to_thread(vpn_manager.stop)
    if settings.vpn_enabled:
        await enforce_vpn_isolation()
        result["started_apps"] = []
    else:
        result["started_apps"] = await start_tunneled_apps(stopped or None)
    return result


@router.post("/restart")
async def vpn_restart(request: Request) -> dict[str, Any]:
    """Bounce the tunnel while keeping VPN enabled (kill switch stays on)."""
    _ensure_authenticated(request)
    from core.integrations.lifecycle import enforce_vpn_isolation, start_tunneled_apps, stop_tunneled_apps

    _persist_vpn_policy(enabled=True)
    stopped = await stop_tunneled_apps()
    await asyncio.to_thread(vpn_manager.stop)
    result = await asyncio.to_thread(vpn_manager.start)
    if result.get("tunnel_up"):
        result["started_apps"] = await start_tunneled_apps(stopped)
    else:
        await enforce_vpn_isolation()
        result["started_apps"] = []
    result["status"] = "restarted" if result.get("tunnel_up") else result.get("status") or "error"
    return result
