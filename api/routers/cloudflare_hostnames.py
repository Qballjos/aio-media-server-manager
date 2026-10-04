"""Public hostname map + Cloudflare Tunnel publish from the Settings UI."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from core.auth import auth_manager
from core.cloudflare_api import (
    CloudflareApiError,
    api_token_configured,
    decode_tunnel_token,
    publish_hostnames,
    set_api_token,
    verify_api_access,
)
from core.cloudflare_api import planned_routes
from core.homepage import clear_homepage_snapshot_cache
from core.public_hostnames import PublicHostnameError, load_hostnames, save_hostnames
from core.settings import settings

router = APIRouter(prefix="/api/cloudflare/hostnames", tags=["Cloudflare Hostnames"])


def _ensure_authenticated(request: Request) -> None:
    if not auth_manager.setup_required():
        auth_manager.authenticate_request(request)


class HostnameEntry(BaseModel):
    subdomain: str = Field(min_length=1, max_length=63)
    enabled: bool = True


class HostnamesPut(BaseModel):
    hostnames: dict[str, HostnameEntry]
    public_app_base_domain: Optional[str] = None
    cloudflare_api_token: Optional[str] = None


class PublishBody(BaseModel):
    hostnames: Optional[dict[str, HostnameEntry]] = None
    public_app_base_domain: Optional[str] = None


def _entries_as_dict(raw: dict[str, HostnameEntry] | None) -> dict[str, dict[str, Any]] | None:
    if raw is None:
        return None
    return {name: {"subdomain": row.subdomain, "enabled": row.enabled} for name, row in raw.items()}


@router.get("")
async def list_hostnames(request: Request) -> dict[str, Any]:
    _ensure_authenticated(request)
    tunnel_ids: dict[str, str] = {}
    tunnel_decode_error = ""
    try:
        tunnel_ids = decode_tunnel_token()
    except CloudflareApiError as exc:
        tunnel_decode_error = str(exc)
    return {
        "public_app_base_domain": settings.public_app_base_domain,
        "api_token_configured": api_token_configured(),
        "tunnel_account_id": tunnel_ids.get("account_id", ""),
        "tunnel_id": tunnel_ids.get("tunnel_id", ""),
        "tunnel_decode_error": tunnel_decode_error,
        "routes": planned_routes(),
        "stored": load_hostnames(),
    }


@router.put("")
async def put_hostnames(request: Request, body: HostnamesPut) -> dict[str, Any]:
    _ensure_authenticated(request)
    if body.public_app_base_domain is not None:
        domain = body.public_app_base_domain.strip().strip(".").lower()
        if domain and ("://" in domain or "/" in domain):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="public_app_base_domain is a DNS zone only (e.g. example.com), not a URL.",
            )
        settings.public_app_base_domain = domain
        settings.save()
    if body.cloudflare_api_token is not None:
        token = body.cloudflare_api_token.strip()
        # Empty string clears; omit field to keep.
        set_api_token(token)
    try:
        saved = save_hostnames(_entries_as_dict(body.hostnames) or {})
    except PublicHostnameError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    clear_homepage_snapshot_cache()
    return {
        "ok": True,
        "public_app_base_domain": settings.public_app_base_domain,
        "api_token_configured": api_token_configured(),
        "routes": planned_routes(hostnames=saved),
        "stored": saved,
    }


@router.post("/publish")
async def publish(request: Request, body: PublishBody | None = None) -> dict[str, Any]:
    _ensure_authenticated(request)
    body = body or PublishBody()
    if body.public_app_base_domain is not None:
        domain = body.public_app_base_domain.strip().strip(".").lower()
        if domain and ("://" in domain or "/" in domain):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="public_app_base_domain is a DNS zone only (e.g. example.com), not a URL.",
            )
        settings.public_app_base_domain = domain
        settings.save()
    host_map = _entries_as_dict(body.hostnames)
    if host_map is not None:
        try:
            host_map = save_hostnames(host_map)
        except PublicHostnameError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    try:
        result = await publish_hostnames(hostnames=host_map)
    except CloudflareApiError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    clear_homepage_snapshot_cache()
    return result


@router.post("/verify")
async def verify(request: Request) -> dict[str, Any]:
    _ensure_authenticated(request)
    try:
        return await verify_api_access()
    except CloudflareApiError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
