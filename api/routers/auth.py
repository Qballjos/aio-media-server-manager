"""
api/routers/auth.py — Authentication Endpoints

Handles initial setup, login, logout, session status, and profile info.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional
from urllib.parse import quote, urlencode

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field
from webauthn import (
    base64url_to_bytes,
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import bytes_to_base64url, parse_client_data_json
from webauthn.helpers.exceptions import WebAuthnException
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from core.auth import COOKIE_CSRF, auth_manager, normalize_email
from core import profile as profile_mod
from core.passkeys import Purpose, relying_party
from core.shared_credentials import save_shared_admin_credentials, shared_admin_credentials

logger = logging.getLogger(__name__)

class AuthRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def handle(request: Request) -> Response:
            try:
                return await handler(request)
            except RequestValidationError as exc:
                # Validation must not echo submitted passwords or authenticator material.
                errors = [{key: item[key] for key in ("loc", "msg", "type")} for item in exc.errors()]
                raise HTTPException(status_code=422, detail=errors) from None

        return handle


router = APIRouter(prefix="/api/auth", tags=["Auth"], route_class=AuthRoute)


class SetupRequest(BaseModel):
    username: str = Field(default="admin", min_length=1)
    password: str = Field(min_length=8)
    email: str = Field(min_length=3)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)
    code: str = Field(default="", max_length=128)


class TwoFactorSetup(BaseModel):
    password: str = Field(min_length=1, max_length=72)


class TwoFactorEnable(BaseModel):
    enrollment: str = Field(min_length=1, max_length=512)
    code: str = Field(min_length=1, max_length=128)


class TwoFactorDisable(TwoFactorSetup):
    code: str = Field(min_length=1, max_length=128)


def _person_fields() -> dict[str, Optional[str]]:
    return {
        "first_name": auth_manager.first_name() or None,
        "last_name": auth_manager.last_name() or None,
    }


class AuthStatusResponse(BaseModel):
    setup_required: bool
    authenticated: bool
    username: Optional[str] = None
    email: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    csrf_token: Optional[str] = None
    avatar_url: Optional[str] = None
    theme: Optional[str] = None
    locale: Optional[str] = None
    wallpaper: Optional[str] = None
    wallpaper_url: Optional[str] = None
    has_wallpaper_image: Optional[bool] = None
    homepage_widget_debug: Optional[bool] = None
    homepage_layout: Optional[list[str]] = None
    homepage_hidden: Optional[list[str]] = None
    homepage_sizes: Optional[dict[str, int]] = None
    homepage_grid: Optional[dict[str, list[dict[str, Any]]]] = None
    glass_alpha: Optional[float] = None
    glass_blur: Optional[int] = None
    glass_depth: Optional[float] = None
    wallpaper_blur: Optional[int] = None


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
        "first_name": None,
        "last_name": None,
        "csrf_token": None,
        "avatar_url": None,
        "theme": None,
        "locale": None,
        "wallpaper": None,
        "wallpaper_url": None,
        "has_wallpaper_image": None,
        "homepage_widget_debug": None,
        "homepage_layout": None,
        "homepage_hidden": None,
        "homepage_sizes": None,
        "homepage_grid": None,
        "glass_alpha": None,
        "glass_blur": None,
        "glass_depth": None,
        "wallpaper_blur": None,
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
            **_person_fields(),
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
        "first_name": None,
        "last_name": None,
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

    if auth_manager.two_factor_enabled():
        if not req.code.strip():
            response.headers["Cache-Control"] = "no-store"
            return {"status": "two_factor_required"}
        if not auth_manager.verify_two_factor(req.code):
            raise HTTPException(status_code=401, detail="Invalid or already used verification code.")

    save_shared_admin_credentials(req.username, req.password)
    return _login_session(response, req.username)


def _login_session(response: Response, username: str) -> dict:
    response.headers["Cache-Control"] = "no-store"
    token = auth_manager.issue_token(username)
    csrf = auth_manager.set_session_cookies(response, token)
    visuals = _visuals_payload()
    return {
        "status": "ok",
        "username": username,
        **_person_fields(),
        "csrf_token": csrf,
        "access_token": token,
        "avatar_url": _avatar_url(),
        **visuals,
    }


def _check_two_factor_password(request: Request, password: str) -> str:
    username = auth_manager.authenticate_request(request)
    auth_manager.check_login_rate(request)
    if not auth_manager.verify_password(username, password):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    return username


def _refresh_two_factor_session(response: Response, username: str) -> dict:
    response.headers["Cache-Control"] = "no-store"
    token = auth_manager.issue_token(username)
    return {
        "access_token": token,
        "csrf_token": auth_manager.set_session_cookies(response, token),
    }


@router.get("/two-factor")
async def two_factor_status(request: Request) -> dict:
    auth_manager.authenticate_request(request)
    return {"enabled": auth_manager.two_factor_enabled()}


@router.post("/two-factor/setup")
async def two_factor_setup(req: TwoFactorSetup, request: Request, response: Response) -> dict:
    username = _check_two_factor_password(request, req.password)
    secret, enrollment = auth_manager.begin_two_factor()
    issuer = "AIO Media Server Manager"
    label = f"{quote(issuer, safe='')}:{quote(username, safe='')}"
    query = urlencode({"secret": secret, "issuer": issuer})
    response.headers["Cache-Control"] = "no-store"
    return {"secret": secret, "uri": f"otpauth://totp/{label}?{query}", "enrollment": enrollment}


@router.post("/two-factor/enable")
async def two_factor_enable(req: TwoFactorEnable, request: Request, response: Response) -> dict:
    username = auth_manager.authenticate_request(request)
    auth_manager.check_login_rate(request)
    codes = auth_manager.enable_two_factor(req.enrollment, req.code)
    return {"recovery_codes": codes, **_refresh_two_factor_session(response, username)}


@router.post("/two-factor/disable")
async def two_factor_disable(req: TwoFactorDisable, request: Request, response: Response) -> dict:
    username = _check_two_factor_password(request, req.password)
    if not auth_manager.verify_two_factor(req.code, disable=True):
        raise HTTPException(status_code=400, detail="Invalid or already used verification code.")
    return _refresh_two_factor_session(response, username)


class PasskeyManagement(TwoFactorSetup):
    code: str = Field(default="", max_length=128)


class PasskeyResponse(BaseModel):
    challenge: str = Field(min_length=1, max_length=128)
    credential: str = Field(min_length=1, max_length=32768)


def _passkey_origin(request: Request) -> tuple[str, str]:
    origin = request.headers.get("Origin", "")
    rp_id = relying_party(origin, request.headers.get("Host", ""))
    if rp_id is None:
        raise HTTPException(status_code=400, detail="Passkeys require the dashboard's HTTPS address.")
    return origin, rp_id


def _check_passkey_factor(code: str) -> None:
    if auth_manager.two_factor_enabled() and not auth_manager.verify_two_factor(code):
        raise HTTPException(status_code=400, detail="Invalid or already used verification code.")


def _take_passkey_challenge(req: PasskeyResponse, purpose: Purpose, origin: str, binding: str) -> bytes:
    challenge = auth_manager.passkey_challenges.take(req.challenge, purpose, origin, binding)
    if challenge is None:
        raise HTTPException(status_code=400, detail="Passkey request expired. Try again.")
    return challenge


def _parse_passkey_response(value: str) -> dict:
    data = json.loads(value)
    client_data = parse_client_data_json(base64url_to_bytes(data["response"]["clientDataJSON"]))
    if client_data.cross_origin:
        raise ValueError("Cross-origin WebAuthn requests are unsupported")
    return data


@router.get("/passkeys")
async def passkey_status(request: Request) -> dict:
    auth_manager.authenticate_request(request)
    passkey = auth_manager.passkey()
    return {"origin": passkey["origin"] if passkey else None, "two_factor_enabled": auth_manager.two_factor_enabled()}


@router.post("/passkeys/register/options")
async def passkey_register_options(req: PasskeyManagement, request: Request, response: Response) -> dict:
    origin, rp_id = _passkey_origin(request)
    username = _check_two_factor_password(request, req.password)
    if auth_manager.passkey():
        raise HTTPException(status_code=409, detail="Remove the current passkey before adding another.")
    _check_passkey_factor(req.code)
    options = generate_registration_options(
        rp_id=rp_id,
        rp_name="AIO Media Server Manager",
        user_name=username,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            require_resident_key=True,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
    )
    auth_manager.passkey_challenges.add(options.challenge, "register", origin, request.state.manager_session_id)
    response.headers["Cache-Control"] = "no-store"
    return json.loads(options_to_json(options))


@router.post("/passkeys/register")
async def passkey_register(req: PasskeyResponse, request: Request) -> dict:
    auth_manager.authenticate_request(request)
    origin, rp_id = _passkey_origin(request)
    challenge = _take_passkey_challenge(req, "register", origin, request.state.manager_session_id)
    if auth_manager.passkey():
        raise HTTPException(status_code=409, detail="Remove the current passkey before adding another.")
    try:
        credential = verify_registration_response(
            credential=_parse_passkey_response(req.credential),
            expected_challenge=challenge,
            expected_origin=origin,
            expected_rp_id=rp_id,
            require_user_verification=True,
        )
    except (WebAuthnException, KeyError, TypeError, ValueError, RecursionError):
        raise HTTPException(status_code=400, detail="Could not verify the passkey.") from None
    auth_manager.save_passkey({
        "origin": origin,
        "id": bytes_to_base64url(credential.credential_id),
        "public_key": bytes_to_base64url(credential.credential_public_key),
        "sign_count": credential.sign_count,
    })
    return {"origin": origin}


@router.post("/passkeys/remove")
async def passkey_remove(req: PasskeyManagement, request: Request) -> dict:
    _check_two_factor_password(request, req.password)
    if auth_manager.passkey():
        _check_passkey_factor(req.code)
        auth_manager.save_passkey(None)
    return {"origin": None}


@router.post("/passkeys/login/options")
async def passkey_login_options(request: Request, response: Response) -> dict:
    origin, rp_id = _passkey_origin(request)
    auth_manager.check_login_rate(request)
    passkey = auth_manager.passkey()
    if auth_manager.setup_required() or not passkey or passkey["origin"] != origin:
        raise HTTPException(status_code=400, detail="No passkey is available at this dashboard address.")
    options = generate_authentication_options(
        rp_id=rp_id,
        allow_credentials=[PublicKeyCredentialDescriptor(id=base64url_to_bytes(passkey["id"]))],
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    auth_manager.passkey_challenges.add(options.challenge, "login", origin, auth_manager.passkey_session_version())
    response.headers["Cache-Control"] = "no-store"
    return json.loads(options_to_json(options))


@router.post("/passkeys/login")
async def passkey_login(req: PasskeyResponse, request: Request, response: Response) -> dict:
    origin, rp_id = _passkey_origin(request)
    auth_manager.check_login_rate(request)
    challenge = _take_passkey_challenge(req, "login", origin, auth_manager.passkey_session_version())
    passkey = auth_manager.passkey()
    if auth_manager.setup_required() or not passkey or passkey["origin"] != origin:
        raise HTTPException(status_code=400, detail="No passkey is available at this dashboard address.")
    try:
        data = _parse_passkey_response(req.credential)
        if data.get("id") != passkey["id"]:
            raise ValueError("Credential ID does not match")
        result = verify_authentication_response(
            credential=data,
            expected_challenge=challenge,
            expected_origin=origin,
            expected_rp_id=rp_id,
            credential_public_key=base64url_to_bytes(passkey["public_key"]),
            credential_current_sign_count=passkey["sign_count"],
            require_user_verification=True,
        )
    except (WebAuthnException, KeyError, TypeError, ValueError, RecursionError):
        raise HTTPException(status_code=400, detail="Could not verify the passkey.") from None
    auth_manager.save_passkey({**passkey, "sign_count": result.new_sign_count})
    return _login_session(response, auth_manager.username())


@router.post("/logout", summary="End session")
async def logout(request: Request, response: Response) -> dict:
    """Revoke this session, then clear its cookies."""
    auth_manager.revoke_request_session(request)
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
        **_person_fields(),
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
    locale: Optional[str] = None
    wallpaper: Optional[str] = None
    homepage_widget_debug: Optional[bool] = None
    homepage_layout: Optional[list[str]] = Field(default=None, max_length=20)
    homepage_hidden: Optional[list[str]] = Field(default=None, max_length=20)
    homepage_sizes: Optional[dict[str, int]] = None
    homepage_grid: Optional[dict[str, Any]] = None
    glass_alpha: Optional[float] = Field(default=None, ge=0.15, le=0.9)
    glass_blur: Optional[int] = Field(default=None, ge=0, le=60)
    glass_depth: Optional[float] = Field(default=None, ge=0, le=2)
    wallpaper_blur: Optional[int] = Field(default=None, ge=0, le=40)


@router.patch("/visuals", summary="Update admin visual preferences")
async def patch_visuals(body: VisualsPatch, request: Request) -> dict:
    auth_manager.authenticate_request(request)
    if all(value is None for value in body.model_dump().values()):
        raise HTTPException(
            status_code=422,
            detail="Provide theme, locale, wallpaper, homepage_widget_debug, homepage_layout, homepage_hidden, homepage_sizes, homepage_grid or a glass_* value.",
        )
    if body.theme is not None and body.theme not in profile_mod.THEMES:
        raise HTTPException(status_code=422, detail="theme must be dark, light, or system.")
    if body.locale is not None and body.locale not in profile_mod.LOCALES:
        raise HTTPException(status_code=422, detail="locale must be en, nl, de, or fr.")
    if body.wallpaper is not None and body.wallpaper not in profile_mod.WALLPAPERS:
        raise HTTPException(
            status_code=422,
            detail="wallpaper must be one of: " + ", ".join(sorted(profile_mod.WALLPAPERS)) + ".",
        )
    visuals = profile_mod.save_visual_preferences(
        theme=body.theme,
        locale=body.locale,
        wallpaper=body.wallpaper,
        homepage_widget_debug=body.homepage_widget_debug,
        homepage_layout=body.homepage_layout,
        homepage_hidden=body.homepage_hidden,
        homepage_sizes=body.homepage_sizes,
        homepage_grid=body.homepage_grid,
        glass_alpha=body.glass_alpha,
        glass_blur=body.glass_blur,
        glass_depth=body.glass_depth,
        wallpaper_blur=body.wallpaper_blur,
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


class ProfilePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: Optional[str] = Field(default=None, min_length=1, max_length=80)
    email: Optional[str] = None
    first_name: Optional[str] = Field(default=None, max_length=80)
    last_name: Optional[str] = Field(default=None, max_length=80)


@router.patch("/profile", summary="Update profile without changing the password")
async def update_profile(req: ProfilePatch, request: Request, response: Response) -> dict:
    username = auth_manager.authenticate_request(request)
    updated = auth_manager.update_profile(username, **req.model_dump(exclude_unset=True))
    shared = shared_admin_credentials()
    if shared:
        save_shared_admin_credentials(updated["username"], shared[1], email=updated["email"])
    token = auth_manager.issue_token(updated["username"])
    csrf = auth_manager.set_session_cookies(response, token)
    return {
        "status": "ok", **updated, "csrf_token": csrf,
        "access_token": token, "avatar_url": _avatar_url(),
    }


class AccountPatch(BaseModel):
    current_password: str = Field(min_length=1)
    username: Optional[str] = None
    email: Optional[str] = None
    first_name: Optional[str] = Field(default=None, max_length=80)
    last_name: Optional[str] = Field(default=None, max_length=80)
    new_password: Optional[str] = Field(default=None, min_length=8)


@router.patch("/account", summary="Update admin username, email, name, or password")
async def update_account(req: AccountPatch, request: Request, response: Response) -> dict:
    username = auth_manager.authenticate_request(request)
    updated = auth_manager.update_account(
        username,
        current_password=req.current_password,
        email=req.email,
        new_username=req.username,
        new_password=req.new_password,
        first_name=req.first_name,
        last_name=req.last_name,
    )
    password_for_share = req.new_password or req.current_password
    save_shared_admin_credentials(updated["username"], password_for_share, email=updated.get("email") or "")
    token = auth_manager.issue_token(updated["username"])
    csrf = auth_manager.set_session_cookies(response, token)
    return {
        "status": "ok",
        "username": updated["username"],
        "email": updated.get("email") or None,
        "first_name": updated.get("first_name") or None,
        "last_name": updated.get("last_name") or None,
        "csrf_token": csrf,
        "access_token": token,
        "avatar_url": _avatar_url(),
    }
