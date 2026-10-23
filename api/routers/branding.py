"""Public branding read + authenticated title/image management."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Request, status
from pathlib import Path

from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from core.auth import auth_manager
from core import branding as branding_mod

router = APIRouter(prefix="/api/branding", tags=["Branding"])


class BrandingPatch(BaseModel):
    title: Optional[str] = Field(default=None, max_length=branding_mod.MAX_TITLE_LEN)
    accent_color: Optional[str] = Field(default=None, max_length=16)
    login_message: Optional[str] = Field(default=None, max_length=branding_mod.MAX_LOGIN_MESSAGE_LEN)


def _ensure_authenticated(request: Request) -> str:
    if auth_manager.setup_required():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Setup required.")
    return auth_manager.authenticate_request(request)


@router.get("", summary="Public branding (title and image URLs)")
async def get_branding() -> dict:
    return branding_mod.public_branding()


@router.get("/file/{slot}", summary="Serve a custom branding image")
async def get_branding_file(slot: str):
    if slot not in branding_mod.SLOTS:
        raise HTTPException(status_code=404, detail="Unknown branding slot.")
    resolved = branding_mod.file_for_slot(slot)
    if resolved is None:
        raise HTTPException(status_code=404, detail="No custom image for this slot.")
    path, mime = resolved
    return FileResponse(
        path,
        media_type=mime,
        headers={"Cache-Control": "public, max-age=86400"},
    )


_STATIC_ROOTS = [Path(__file__).resolve().parents[2] / "frontend" / sub for sub in ("dist", "public")]


@router.get("/icon/{kind}", summary="The tab or home-screen icon: the custom favicon, else the default")
async def get_app_icon(kind: str):
    try:
        custom, mime, default = branding_mod.app_icon(kind)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    # no-cache: browsers keep icons for a long time; revalidating (ETag) lets a new upload show up.
    headers = {"Cache-Control": "no-cache"}
    if custom is not None:
        return FileResponse(custom, media_type=mime, headers=headers)
    for root in _STATIC_ROOTS:
        if (root / default.lstrip("/")).is_file():
            return FileResponse(root / default.lstrip("/"), media_type="image/png", headers=headers)
    return RedirectResponse(default)


@router.get("/manifest.webmanifest", summary="PWA manifest with the configured title and favicon")
async def get_web_manifest():
    return JSONResponse(
        branding_mod.web_manifest(),
        media_type="application/manifest+json",
        headers={"Cache-Control": "no-cache"},
    )


@router.patch("", summary="Update brand title and/or accent color")
async def patch_branding(body: BrandingPatch, request: Request) -> dict:
    _ensure_authenticated(request)
    if body.title is None and body.accent_color is None and body.login_message is None:
        raise HTTPException(status_code=400, detail="No branding fields to update.")
    if body.title is not None:
        branding_mod.set_title(body.title)
    if body.accent_color is not None:
        try:
            branding_mod.set_accent(body.accent_color)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    if body.login_message is not None:
        branding_mod.set_login_message(body.login_message)
    return branding_mod.public_branding()


@router.put("/{slot}", summary="Upload a branding image")
async def put_branding_image(slot: str, request: Request) -> dict:
    _ensure_authenticated(request)
    if slot not in branding_mod.SLOTS:
        raise HTTPException(status_code=404, detail="Unknown branding slot.")
    data = await request.body()
    try:
        return branding_mod.save_slot(slot, data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/{slot}", summary="Reset a branding image to the default")
async def delete_branding_image(slot: str, request: Request) -> dict:
    _ensure_authenticated(request)
    if slot not in branding_mod.SLOTS:
        raise HTTPException(status_code=404, detail="Unknown branding slot.")
    try:
        return branding_mod.clear_slot(slot)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
