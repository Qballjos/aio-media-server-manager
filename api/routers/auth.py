"""
api/routers/auth.py — Authentication Endpoints

Handles initial setup, login, logout, session status, and profile info.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from core.auth import COOKIE_CSRF, auth_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["Auth"])


class SetupRequest(BaseModel):
    username: str = Field(default="admin", min_length=1)
    password: str = Field(min_length=8)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class AuthStatusResponse(BaseModel):
    setup_required: bool
    authenticated: bool
    username: Optional[str] = None
    csrf_token: Optional[str] = None


@router.get("/status", response_model=AuthStatusResponse, summary="Check auth status")
async def auth_status(request: Request) -> dict:
    """
    Returns whether initial admin account setup is required, and whether
    the current client has an active authenticated session.
    """
    needs_setup = auth_manager.setup_required()
    if needs_setup:
        return {
            "setup_required": True,
            "authenticated": False,
            "username": None,
            "csrf_token": None,
        }

    try:
        username = auth_manager.authenticate_request(request)
        return {
            "setup_required": False,
            "authenticated": True,
            "username": username,
            "csrf_token": request.cookies.get(COOKIE_CSRF),
        }
    except HTTPException:
        return {
            "setup_required": False,
            "authenticated": False,
            "username": None,
            "csrf_token": None,
        }


@router.post("/setup", summary="Create initial admin account")
async def setup_admin(req: SetupRequest, response: Response) -> dict:
    """
    Creates the first local administrator account if none exists.
    """
    auth_manager.create_admin(username=req.username, password=req.password)
    token = auth_manager.issue_token(req.username)
    csrf = auth_manager.set_session_cookies(response, token)
    return {
        "status": "ok",
        "username": req.username,
        "csrf_token": csrf,
        "access_token": token,
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

    token = auth_manager.issue_token(req.username)
    csrf = auth_manager.set_session_cookies(response, token)
    return {
        "status": "ok",
        "username": req.username,
        "csrf_token": csrf,
        "access_token": token,
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
    return {"username": username}
