"""
core/auth.py — Local admin authentication, JWT sessions, CSRF, rate limiting.
"""

from __future__ import annotations

import logging
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import bcrypt
import jwt
from fastapi import HTTPException, Request, Response, status

from core.settings import Settings, settings

logger = logging.getLogger(__name__)

COOKIE_ACCESS = "amm_access"
COOKIE_CSRF = "amm_csrf"
CSRF_HEADER = "X-CSRF-Token"
JWT_ALGORITHM = "HS256"
JWT_TTL_SECONDS = 60 * 60 * 24 * 7  # 7 days
MIN_PASSWORD_LENGTH = 8
LOGIN_WINDOW_SECONDS = 15 * 60
LOGIN_MAX_ATTEMPTS = 10
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


@dataclass
class RateLimiter:
    window_seconds: int = LOGIN_WINDOW_SECONDS
    max_attempts: int = LOGIN_MAX_ATTEMPTS
    _hits: dict[str, list[float]] = field(default_factory=dict)

    def allow(self, key: str) -> bool:
        now = time.time()
        stamps = [ts for ts in self._hits.get(key, []) if now - ts < self.window_seconds]
        if len(stamps) >= self.max_attempts:
            self._hits[key] = stamps
            return False
        stamps.append(now)
        self._hits[key] = stamps
        return True

    def remaining(self, key: str) -> int:
        now = time.time()
        stamps = [ts for ts in self._hits.get(key, []) if now - ts < self.window_seconds]
        return max(0, self.max_attempts - len(stamps))


class AuthManager:
    """Filesystem-backed admin password and JWT/CSRF helpers."""

    def __init__(self, app_settings: Settings = settings) -> None:
        self._settings = app_settings
        self._rate = RateLimiter()

    @property
    def _secret_path(self) -> Path:
        return self._settings.config_dir / ".jwt_secret"

    @property
    def _auth_path(self) -> Path:
        return self._settings.config_dir / "auth.json"

    def jwt_secret(self) -> str:
        path = self._secret_path
        if path.is_file():
            return path.read_text(encoding="utf-8").strip()
        path.parent.mkdir(parents=True, exist_ok=True)
        secret = secrets.token_urlsafe(48)
        path.write_text(secret, encoding="utf-8")
        try:
            path.chmod(0o600)
        except OSError:
            pass
        return secret

    def _read_auth(self) -> dict[str, Any]:
        path = self._auth_path
        if not path.is_file():
            return {}
        import json

        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _write_auth(self, payload: dict[str, Any]) -> None:
        import json

        path = self._auth_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        try:
            path.chmod(0o600)
        except OSError:
            pass

    def setup_required(self) -> bool:
        return not bool(self._read_auth().get("password_hash"))

    def username(self) -> str:
        return str(self._read_auth().get("username") or "admin")

    def create_admin(self, username: str, password: str) -> None:
        if not self.setup_required():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Admin account already exists.",
            )
        self._validate_password(password)
        hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
        self._write_auth(
            {
                "username": username.strip() or "admin",
                "password_hash": hashed.decode("utf-8"),
            }
        )
        logger.info("Created local admin account '%s'.", username)

    def verify_password(self, username: str, password: str) -> bool:
        data = self._read_auth()
        stored_user = data.get("username") or "admin"
        stored_hash = data.get("password_hash")
        if not stored_hash or username != stored_user:
            return False
        try:
            return bcrypt.checkpw(
                password.encode("utf-8"),
                stored_hash.encode("utf-8"),
            )
        except ValueError:
            return False

    def issue_token(self, username: str) -> str:
        now = int(time.time())
        payload = {
            "sub": username,
            "iat": now,
            "exp": now + JWT_TTL_SECONDS,
        }
        return jwt.encode(payload, self.jwt_secret(), algorithm=JWT_ALGORITHM)

    def decode_token(self, token: str) -> dict[str, Any]:
        try:
            return jwt.decode(token, self.jwt_secret(), algorithms=[JWT_ALGORITHM])
        except jwt.PyJWTError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired session.",
            ) from exc

    def set_session_cookies(self, response: Response, token: str) -> str:
        csrf = secrets.token_urlsafe(32)
        secure = False  # HTTP-first appliance; reverse-proxy TLS comes later
        response.set_cookie(
            COOKIE_ACCESS,
            token,
            httponly=True,
            samesite="lax",
            secure=secure,
            max_age=JWT_TTL_SECONDS,
            path="/",
        )
        response.set_cookie(
            COOKIE_CSRF,
            csrf,
            httponly=False,
            samesite="lax",
            secure=secure,
            max_age=JWT_TTL_SECONDS,
            path="/",
        )
        return csrf

    def clear_session_cookies(self, response: Response) -> None:
        response.delete_cookie(COOKIE_ACCESS, path="/")
        response.delete_cookie(COOKIE_CSRF, path="/")

    def check_login_rate(self, request: Request) -> None:
        key = request.client.host if request.client else "unknown"
        if not self._rate.allow(key):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many login attempts. Try again later.",
            )

    def authenticate_request(self, request: Request) -> str:
        token = request.cookies.get(COOKIE_ACCESS)
        using_bearer = False

        if not token:
            auth_header = request.headers.get("Authorization", "").strip()
            if auth_header.startswith("Bearer "):
                token = auth_header[7:].strip()
                using_bearer = True

        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required.",
            )

        payload = self.decode_token(token)
        username = str(payload.get("sub") or "")
        if not username:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required.",
            )

        # Enforce CSRF only on ambient cookie authentication for mutating methods
        if not using_bearer and request.method.upper() not in _SAFE_METHODS:
            header = request.headers.get(CSRF_HEADER, "")
            cookie = request.cookies.get(COOKIE_CSRF, "")
            if not header or not cookie or not secrets.compare_digest(header, cookie):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="CSRF token missing or invalid.",
                )
        return username

    @staticmethod
    def _validate_password(password: str) -> None:
        if len(password) < MIN_PASSWORD_LENGTH:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Password must be at least {MIN_PASSWORD_LENGTH} characters.",
            )


auth_manager = AuthManager()
