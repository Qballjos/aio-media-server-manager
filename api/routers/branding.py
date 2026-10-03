"""Public branding read + authenticated title/image management."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from core.auth import auth_manager
from core import branding as branding_mod

router = APIRouter(prefix="/api/branding", tags=["Branding"])


class BrandingPatch(BaseModel):
    title: Optional[str] = Field(default=None, max_length=branding_mod.MAX_TITLE_LEN)
    accent_color: Optional[str] = Field(default=None, max_length=16)


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


@router.patch("", summary="Update brand title and/or accent color")
async def patch_branding(body: BrandingPatch, request: Request) -> dict:
    _ensure_authenticated(request)
    if body.title is None and body.accent_color is None:
        raise HTTPException(status_code=400, detail="No branding fields to update.")
    if body.title is not None:
        branding_mod.set_title(body.title)
    if body.accent_color is not None:
        try:
            branding_mod.set_accent(body.accent_color)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
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
