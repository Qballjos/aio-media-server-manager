"""Usenet provider (news server) and NZB indexers after the first run."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
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


class UsenetIndexerBody(BaseModel):
    name: str = Field(default="", max_length=80)
    url: str = Field(min_length=4, max_length=300)
    api_key: str = Field(min_length=1, max_length=200)


def _ensure_authenticated(request: Request) -> None:
    if not auth_manager.setup_required():
        auth_manager.authenticate_request(request)


def _usenet_clients() -> list[str]:
    from applications.catalog import ApplicationCatalog

    catalog = ApplicationCatalog()
    return [name for name in ("sabnzbd", "nzbget") if catalog.has(name) and catalog.get(name).is_installed()]


def _prowlarr() -> Any:
    from applications.catalog import ApplicationCatalog
    from core.integrations.credentials import get_application_api_key
    from core.integrations.prowlarr import ProwlarrClient

    catalog = ApplicationCatalog()
    if not (catalog.has("prowlarr") and catalog.get("prowlarr").is_installed()):
        return None
    return ProwlarrClient(port=catalog.get("prowlarr").port, api_key=get_application_api_key("prowlarr"))


def _prowlarr_usenet_indexers() -> list[dict[str, str]] | None:
    client = _prowlarr()
    return client.usenet_indexers() if client else None


@router.get("", summary="Usenet provider and NZB indexers")
async def get_usenet(request: Request) -> dict[str, Any]:
    _ensure_authenticated(request)
    indexers = await asyncio.to_thread(_prowlarr_usenet_indexers)
    return {
        "server": public_usenet_server(),
        "clients": await asyncio.to_thread(_usenet_clients),
        "prowlarr": indexers is not None,
        "indexers": indexers or [],
    }


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


@router.post("/indexers", summary="Add a Newznab indexer to Prowlarr")
async def add_usenet_indexer(body: UsenetIndexerBody, request: Request) -> dict[str, Any]:
    _ensure_authenticated(request)
    client = await asyncio.to_thread(_prowlarr)
    if client is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Install Prowlarr to add Usenet indexers.")
    ok, detail = await asyncio.to_thread(client.add_newznab_indexer, name=body.name, url=body.url, api_key=body.api_key)
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
    return {"detail": detail, "indexers": await asyncio.to_thread(client.usenet_indexers)}
