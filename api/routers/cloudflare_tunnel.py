"""Cloudflare Tunnel (cloudflared) status and control."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from core.auth import auth_manager
from core.cloudflare_tunnel import cloudflare_tunnel

router = APIRouter(prefix="/api/cloudflare/tunnel", tags=["Cloudflare Tunnel"])


def _ensure_authenticated(request: Request) -> None:
    if not auth_manager.setup_required():
        auth_manager.authenticate_request(request)


@router.get("/status")
async def tunnel_status(request: Request) -> dict[str, Any]:
    _ensure_authenticated(request)
    return cloudflare_tunnel.status()


@router.post("/start")
async def tunnel_start(request: Request) -> dict[str, Any]:
    _ensure_authenticated(request)
    return await cloudflare_tunnel.start()


@router.post("/stop")
async def tunnel_stop(request: Request) -> dict[str, Any]:
    _ensure_authenticated(request)
    return await cloudflare_tunnel.stop()
