"""
api/routers/auth.py — Authentication Endpoints

Handles initial setup, login, logout, session status, and profile info.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from core.auth import COOKIE_CSRF, auth_manager, normalize_email
from core import profile as profile_mod
from core.shared_credentials import save_shared_admin_credentials

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["Auth"])


class SetupRequest(BaseModel):
    username: str = Field(default="admin", min_length=1)
    password: str = Field(min_length=8)
    email: str = Field(min_length=3)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class AuthStatusResponse(BaseModel):
    setup_required: bool
    authenticated: bool
    username: Optional[str] = None
    email: Optional[str] = None
    csrf_token: Optional[str] = None
    avatar_url: Optional[str] = None
    theme: Optional[str] = None
    wallpaper: Optional[str] = None
    wallpaper_url: Optional[str] = None
    has_wallpaper_image: Optional[bool] = None
    homepage_widget_debug: Optional[bool] = None


def _avatar_url() -> str | None:
    return profile_mod.avatar_url()


def _visuals_payload() -> dict:
    return profile_mod.visual_preferences()


def _empty_auth(*, setup_required: bool) -> dict:
    return {
        "setup_required": setup_required,
        "authenticated": False,
        "username": None,
        "email": None,
        "csrf_token": None,
        "avatar_url": None,
        "theme": None,
        "wallpaper": None,
        "wallpaper_url": None,
        "has_wallpaper_image": None,
        "homepage_widget_debug": None,
    }


@router.get("/status", response_model=AuthStatusResponse, summary="Check auth status")
async def auth_status(request: Request) -> dict:
    """
    Returns whether initial admin account setup is required, and whether
    the current client has an active authenticated session.
    """
    needs_setup = auth_manager.setup_required()
    if needs_setup:
        return _empty_auth(setup_required=True)

    try:
        username = auth_manager.authenticate_request(request)
        visuals = _visuals_payload()
        return {
            "setup_required": False,
            "authenticated": True,
            "username": username,
            "email": auth_manager.email() or None,
            "csrf_token": request.cookies.get(COOKIE_CSRF),
            "avatar_url": _avatar_url(),
            **visuals,
        }
    except HTTPException:
        return _empty_auth(setup_required=False)


@router.post("/setup", summary="Create initial admin account")
async def setup_admin(req: SetupRequest, response: Response) -> dict:
    """
    Creates the first local administrator account if none exists.
    """
    email = normalize_email(req.email)
    auth_manager.create_admin(username=req.username, password=req.password, email=email)
    save_shared_admin_credentials(req.username, req.password, email=email)
    token = auth_manager.issue_token(req.username)
    csrf = auth_manager.set_session_cookies(response, token)
    visuals = _visuals_payload()
    return {
        "status": "ok",
        "username": req.username,
        "email": email,
        "csrf_token": csrf,
        "access_token": token,
        "avatar_url": _avatar_url(),
        **visuals,
    }


@router.post("/login", summary="Login with username and password")
async def login(req: LoginRequest, request: Request, response: Response) -> dict:
    """
    Authenticate against local admin credentials, establishing a session.
    """
    if auth_manager.setup_required():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admin account not yet configured. Please complete setup first.",
        )

    auth_manager.check_login_rate(request)

    if not auth_manager.verify_password(req.username, req.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )

    save_shared_admin_credentials(req.username, req.password)

    token = auth_manager.issue_token(req.username)
    csrf = auth_manager.set_session_cookies(response, token)
    visuals = _visuals_payload()
    return {
        "status": "ok",
        "username": req.username,
        "csrf_token": csrf,
        "access_token": token,
        "avatar_url": _avatar_url(),
        **visuals,
    }


@router.post("/logout", summary="End session")
async def logout(response: Response) -> dict:
    """Clear session cookies."""
    auth_manager.clear_session_cookies(response)
    return {"status": "ok"}


@router.get("/me", summary="Current user profile")
async def get_current_user(request: Request) -> dict:
    """Return profile for the currently authenticated user."""
    username = auth_manager.authenticate_request(request)
    profile = profile_mod.public_profile()
    return {
        "username": username,
        "email": auth_manager.email() or None,
        **profile,
    }


@router.get("/avatar", summary="Serve the admin profile image")
async def get_avatar(request: Request):
    auth_manager.authenticate_request(request)
    resolved = profile_mod.avatar_file()
    if resolved is None:
        raise HTTPException(status_code=404, detail="No profile image set.")
    path, mime = resolved
    return FileResponse(
        path,
        media_type=mime,
        headers={"Cache-Control": "private, max-age=86400"},
    )


@router.put("/avatar", summary="Upload the admin profile image")
async def put_avatar(request: Request) -> dict:
    auth_manager.authenticate_request(request)
    data = await request.body()
    try:
        profile = profile_mod.save_avatar(data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "status": "ok",
        "username": auth_manager.username(),
        "email": auth_manager.email() or None,
        **profile,
    }


@router.delete("/avatar", summary="Remove the admin profile image")
async def delete_avatar(request: Request) -> dict:
    auth_manager.authenticate_request(request)
    profile = profile_mod.clear_avatar()
    return {
        "status": "ok",
        "username": auth_manager.username(),
        "email": auth_manager.email() or None,
        **profile,
    }


class VisualsPatch(BaseModel):
    theme: Optional[str] = None
    wallpaper: Optional[str] = None
    homepage_widget_debug: Optional[bool] = None


@router.patch("/visuals", summary="Update admin visual preferences")
async def patch_visuals(body: VisualsPatch, request: Request) -> dict:
    auth_manager.authenticate_request(request)
    if body.theme is None and body.wallpaper is None and body.homepage_widget_debug is None:
        raise HTTPException(
            status_code=422,
            detail="Provide theme, wallpaper, and/or homepage_widget_debug.",
        )
    if body.theme is not None and body.theme not in profile_mod.THEMES:
        raise HTTPException(status_code=422, detail="theme must be dark, light, or system.")
    if body.wallpaper is not None and body.wallpaper not in profile_mod.WALLPAPERS:
        raise HTTPException(
            status_code=422,
            detail="wallpaper must be default, jellyfin, plex, or personal.",
        )
    visuals = profile_mod.save_visual_preferences(
        theme=body.theme,
        wallpaper=body.wallpaper,
        homepage_widget_debug=body.homepage_widget_debug,
    )
    return {"status": "ok", **visuals}


@router.get("/wallpaper", summary="Serve the admin wallpaper image")
async def get_wallpaper(request: Request):
    auth_manager.authenticate_request(request)
    resolved = profile_mod.wallpaper_file()
    if resolved is None:
        raise HTTPException(status_code=404, detail="No wallpaper image set.")
    path, mime = resolved
    return FileResponse(
        path,
        media_type=mime,
        headers={"Cache-Control": "private, max-age=86400"},
    )


@router.put("/wallpaper", summary="Upload the admin wallpaper image")
async def put_wallpaper(request: Request) -> dict:
    auth_manager.authenticate_request(request)
    data = await request.body()
    try:
        visuals = profile_mod.save_wallpaper_image(data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"status": "ok", **visuals}


@router.delete("/wallpaper", summary="Remove the admin wallpaper image")
async def delete_wallpaper(request: Request) -> dict:
    auth_manager.authenticate_request(request)
    visuals = profile_mod.clear_wallpaper_image()
    return {"status": "ok", **visuals}


class AccountPatch(BaseModel):
    current_password: str = Field(min_length=1)
    username: Optional[str] = None
    email: Optional[str] = None
    new_password: Optional[str] = Field(default=None, min_length=8)


@router.patch("/account", summary="Update admin username, email, or password")
async def update_account(req: AccountPatch, request: Request, response: Response) -> dict:
    username = auth_manager.authenticate_request(request)
    updated = auth_manager.update_account(
        username,
        current_password=req.current_password,
        email=req.email,
        new_username=req.username,
        new_password=req.new_password,
    )
    password_for_share = req.new_password or req.current_password
    save_shared_admin_credentials(updated["username"], password_for_share, email=updated.get("email") or "")
    token = auth_manager.issue_token(updated["username"])
    csrf = auth_manager.set_session_cookies(response, token)
    return {
        "status": "ok",
        "username": updated["username"],
        "email": updated.get("email") or None,
        "csrf_token": csrf,
        "access_token": token,
        "avatar_url": _avatar_url(),
    }
