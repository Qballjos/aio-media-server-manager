"""Browser-bound media-account sign-in for limited dashboard sessions."""

import secrets
import time
from dataclasses import dataclass
from threading import Lock
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response

from api.routers.media_users import _client as _seerr_client
from applications.catalog import ApplicationCatalog
from core.auth import auth_manager
from core.integrations.jellyfin import JellyfinClient
from core.integrations.plex_login import begin_plex_sign_in, finish_plex_sign_in
from core.settings import settings

router = APIRouter(prefix="/api/media-login", tags=["Media login"])

_ATTEMPT_COOKIE = "amm_media_attempt"
_ATTEMPT_HEADER = "X-AIO-Media-Attempt"
_ATTEMPT_TTL = 180
_MAX_PENDING = 128


@dataclass(frozen=True)
class MediaAttempt:
    browser: str
    provider: str
    secret: str
    server_id: str
    expires: float


_pending: dict[str, MediaAttempt] = {}
_pending_lock = Lock()


def _remember(key: str, attempt: MediaAttempt) -> None:
    now = time.monotonic()
    with _pending_lock:
        for expired in [key for key, value in _pending.items() if value.expires <= now]:
            del _pending[expired]
        if attempt.expires <= now:
            raise HTTPException(404, "Sign-in attempt expired.")
        if len(_pending) >= _MAX_PENDING:
            del _pending[next(iter(_pending))]
        _pending[key] = attempt


def _take(request: Request, key: str, provider: str) -> MediaAttempt:
    browser = request.cookies.get(_ATTEMPT_COOKIE, "")
    with _pending_lock:
        attempt = _pending.get(key)
        if attempt and attempt.provider == provider and secrets.compare_digest(attempt.browser, browser):
            del _pending[key]
            if attempt.expires > time.monotonic():
                return attempt
    raise HTTPException(404, "Sign-in attempt not found or expired.")


def _media_server_id(expected_provider: str) -> str:
    with _seerr_client() as seerr:
        provider, server_id = seerr.media_user_source()
    if provider != expected_provider:
        raise HTTPException(409, "This provider is not the configured media source in Seerr.")
    return server_id


def _jellyfin_client() -> JellyfinClient:
    return JellyfinClient(port=ApplicationCatalog().get("jellyfin").port)


@router.get("/options")
def media_sign_in_options(response: Response):
    response.headers["Cache-Control"] = "no-store"
    if auth_manager.setup_required() or not auth_manager.media_users.path.is_file():
        return {"provider": None}
    try:
        with _seerr_client() as seerr:
            provider, server_id = seerr.media_user_source()
    except HTTPException:
        return {"provider": None}
    enabled = auth_manager.media_users.versions(provider, server_id)
    return {"provider": provider if enabled else None}


@router.post("/logout", status_code=204)
def logout_member(request: Request, response: Response):
    auth_manager.revoke_request_session(request, member=True)
    auth_manager.clear_session_cookies(response)


@router.post("/{provider}")
def begin_media_sign_in(provider: Literal["jellyfin", "plex"], request: Request, response: Response):
    auth_manager.check_login_rate(request)
    if auth_manager.setup_required():
        raise HTTPException(409, "Complete administrator setup first.")
    server_id = _media_server_id(provider)
    key = secrets.token_hex(24)
    if provider == "jellyfin":
        code, secret = _jellyfin_client().begin_member_sign_in(key)
        prompt = {"code": code}
    else:
        url, secret = begin_plex_sign_in(key)
        prompt = {"authorize_url": url}
    browser = secrets.token_hex(24)
    _remember(key, MediaAttempt(browser, provider, secret, server_id, time.monotonic() + _ATTEMPT_TTL))
    response.set_cookie(
        _ATTEMPT_COOKIE, browser, path="/api/media-login",
        httponly=True, secure=settings.secure_cookies, samesite="lax", max_age=_ATTEMPT_TTL,
    )
    response.headers["Cache-Control"] = "no-store"
    return {"attempt": key, "expires_in": _ATTEMPT_TTL, **prompt}


@router.post("/{provider}/complete")
def complete_media_sign_in(provider: Literal["jellyfin", "plex"], request: Request, response: Response):
    key = request.headers.get(_ATTEMPT_HEADER, "")
    attempt = _take(request, key, provider)
    server_id = attempt.server_id
    if provider == "jellyfin":
        result = _jellyfin_client().finish_member_sign_in(key, attempt.secret)
        if result is not None:
            server_id, account_id, library_token = result
    else:
        result = finish_plex_sign_in(key, attempt.secret, server_id)
        if result is not None:
            account_id, library_token = result
    response.headers["Cache-Control"] = "no-store"
    if result is None:
        _remember(key, attempt)
        response.status_code = 202
        return {"status": "pending"}
    if server_id != attempt.server_id or server_id != _media_server_id(provider):
        raise HTTPException(403, "The account belongs to a different media server.")
    if attempt.expires <= time.monotonic():
        raise HTTPException(404, "Sign-in attempt expired.")
    token = auth_manager.issue_member_token(provider, server_id, account_id, library_token=library_token)
    csrf_token = auth_manager.set_session_cookies(response, token)
    response.delete_cookie(
        _ATTEMPT_COOKIE, path="/api/media-login",
        httponly=True, secure=settings.secure_cookies, samesite="lax",
    )
    return {"account_id": account_id, "csrf_token": csrf_token}


@router.get("/session")
def get_member_session(request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return {"account_id": auth_manager.authenticate_member_request(request)}
