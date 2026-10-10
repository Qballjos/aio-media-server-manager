"""Usenet provider (news server) for Settings → Usenet.

NZB indexers are added by hand in Prowlarr, so this router only handles the provider.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from core.auth import auth_manager
from core.integrations.usenet import load_usenet_server, public_usenet_server, push_usenet_server, save_usenet_server

router = APIRouter(prefix="/api/usenet", tags=["Usenet"])


class UsenetServerBody(BaseModel):
    host: str = Field(min_length=1, max_length=253)
    port: int = Field(default=563, ge=1, le=65535)
    ssl: bool = True
    username: str = Field(default="", max_length=200)
    password: str | None = Field(default=None, max_length=200)  # empty keeps the saved one
    connections: int = Field(default=8, ge=1, le=100)


def _ensure_authenticated(request: Request) -> None:
    if not auth_manager.setup_required():
        auth_manager.authenticate_request(request)


def _usenet_clients() -> list[str]:
    from applications.catalog import ApplicationCatalog

    catalog = ApplicationCatalog()
    return [name for name in ("sabnzbd", "nzbget") if catalog.has(name) and catalog.get(name).is_installed()]


@router.get("", summary="Usenet provider and the clients that use it")
async def get_usenet(request: Request) -> dict[str, Any]:
    _ensure_authenticated(request)
    return {"server": public_usenet_server(), "clients": await asyncio.to_thread(_usenet_clients)}


@router.put("/server", summary="Save the Usenet provider and send it to SABnzbd / NZBGet")
async def put_usenet_server(body: UsenetServerBody, request: Request) -> dict[str, Any]:
    _ensure_authenticated(request)
    previous_host = (load_usenet_server() or {}).get("host", "")
    save_usenet_server(
        host=body.host.strip(),
        port=body.port,
        ssl=body.ssl,
        username=body.username,
        password=body.password or "",
        connections=body.connections,
    )
    applied = await asyncio.to_thread(push_usenet_server, previous_host)
    return {"server": public_usenet_server(), "applied": applied}
