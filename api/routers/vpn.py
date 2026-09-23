"""VPN status and control for torrent traffic only."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from core.auth import auth_manager
from core.vpn import vpn_manager

router = APIRouter(prefix="/api/vpn", tags=["VPN"])


def _ensure_authenticated(request: Request) -> None:
    if not auth_manager.setup_required():
        auth_manager.authenticate_request(request)


@router.get("/status")
async def vpn_status(request: Request) -> dict[str, Any]:
    _ensure_authenticated(request)
    return vpn_manager.status()


@router.post("/start")
async def vpn_start(request: Request) -> dict[str, Any]:
    _ensure_authenticated(request)
    return vpn_manager.start()


@router.post("/stop")
async def vpn_stop(request: Request) -> dict[str, Any]:
    _ensure_authenticated(request)
    return vpn_manager.stop()
