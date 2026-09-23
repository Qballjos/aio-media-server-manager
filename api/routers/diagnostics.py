"""Debug error manager and time-limited share URLs."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, JSONResponse

from core.auth import auth_manager
from core.diagnostics import diagnostics

router = APIRouter(tags=["Diagnostics"])


def _ensure_authenticated(request: Request) -> None:
    if not auth_manager.setup_required():
        auth_manager.authenticate_request(request)


def _share_url(request: Request, token: str) -> str:
    base = str(request.base_url).rstrip("/")
    return f"{base}/debug/{token}"


@router.get("/api/diagnostics", summary="Debug share status and recent errors")
async def diagnostics_status(request: Request) -> dict[str, Any]:
    _ensure_authenticated(request)
    share = diagnostics.share_status()
    token = share.get("token")
    return {
        "share": {
            **share,
            "url": _share_url(request, token) if token else None,
            "ttl_hours": 24,
        },
        "errors": diagnostics.recent_errors(40),
    }


@router.post("/api/diagnostics/share", summary="Create a time-limited debug URL")
async def create_debug_share(request: Request) -> dict[str, Any]:
    _ensure_authenticated(request)
    payload = diagnostics.create_share()
    return {
        "status": "ok",
        "token": payload["token"],
        "expires_at": payload["expires_at"],
        "url": _share_url(request, payload["token"]),
        "ttl_hours": 24,
    }


@router.delete("/api/diagnostics/share", summary="Revoke the debug URL")
async def revoke_debug_share(request: Request) -> dict[str, Any]:
    _ensure_authenticated(request)
    diagnostics.revoke_share()
    return {"status": "revoked"}


@router.get("/debug/{token}", summary="Public debug report (token required)", include_in_schema=False, response_model=None)
async def public_debug_report(
    token: str,
    format: str | None = Query(default=None),
):
    if not diagnostics.validate_token(token):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown or expired debug link.")
    report = diagnostics.build_report()
    if (format or "").lower() == "json":
        return JSONResponse(report)
    return HTMLResponse(diagnostics.render_html(report))
