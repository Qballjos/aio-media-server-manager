"""
tests/test_auth.py — Unit tests for authentication, password hashing, JWT sessions, and CSRF protection.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from core.auth import (
    COOKIE_ACCESS,
    COOKIE_CSRF,
    CSRF_HEADER,
    AuthManager,
    RateLimiter,
)
from core.settings import Settings


@pytest.fixture
def auth_mgr(tmp_path: Path) -> AuthManager:
    """Provides an AuthManager with an isolated config directory."""
    settings = Settings(config_dir=tmp_path / "config")
    return AuthManager(app_settings=settings)


def test_setup_required_initially(auth_mgr: AuthManager):
    """Setup is required when no admin account has been created."""
    assert auth_mgr.setup_required() is True


def test_create_admin_and_verify(auth_mgr: AuthManager):
    """Admin creation hashes password and updates setup status."""
    auth_mgr.create_admin("admin", "AdminPassword123!")
    assert auth_mgr.setup_required() is False
    assert auth_mgr.username() == "admin"

    # Verifying password
    assert auth_mgr.verify_password("admin", "AdminPassword123!") is True
    assert auth_mgr.verify_password("admin", "WrongPassword!") is False
    assert auth_mgr.verify_password("other_user", "AdminPassword123!") is False

    # Second setup should fail with 409 Conflict
    with pytest.raises(HTTPException) as exc_info:
        auth_mgr.create_admin("admin2", "AdminPassword123!")
    assert exc_info.value.status_code == 409


def test_password_min_length_validation(auth_mgr: AuthManager):
    """Password must meet minimum length requirement."""
    with pytest.raises(HTTPException) as exc_info:
        auth_mgr.create_admin("admin", "short")
    assert exc_info.value.status_code == 422


def test_password_max_bcrypt_bytes(auth_mgr: AuthManager):
    """bcrypt 5 rejects secrets longer than 72 bytes."""
    with pytest.raises(HTTPException) as exc_info:
        auth_mgr.create_admin("admin", "x" * 73)
    assert exc_info.value.status_code == 422


def test_jwt_token_issue_and_decode(auth_mgr: AuthManager):
    """JWT tokens can be issued and decoded accurately."""
    token = auth_mgr.issue_token("admin")
    assert isinstance(token, str)

    payload = auth_mgr.decode_token(token)
    assert payload.get("sub") == "admin"
    assert "exp" in payload
    assert "iat" in payload

    # Invalid token raises 401
    with pytest.raises(HTTPException) as exc_info:
        auth_mgr.decode_token("invalid.token.payload")
    assert exc_info.value.status_code == 401


def test_rate_limiter():
    """Rate limiter allows requests under max_attempts and blocks beyond."""
    limiter = RateLimiter(window_seconds=60, max_attempts=3)
    assert limiter.allow("1.2.3.4") is True
    assert limiter.allow("1.2.3.4") is True
    assert limiter.allow("1.2.3.4") is True
    assert limiter.allow("1.2.3.4") is False
    # Other IP should still be allowed
    assert limiter.allow("5.6.7.8") is True


def test_authenticate_request_bearer_token(auth_mgr: AuthManager):
    """Authentication via Authorization: Bearer <token>."""
    token = auth_mgr.issue_token("admin")
    request = MagicMock()
    request.cookies = {}
    request.headers = {"Authorization": f"Bearer {token}"}
    request.method = "GET"

    username = auth_mgr.authenticate_request(request)
    assert username == "admin"


def test_authenticate_request_cookie_and_csrf(auth_mgr: AuthManager):
    """Authentication via cookie requires matching CSRF header for mutating methods."""
    token = auth_mgr.issue_token("admin")
    csrf_secret = "test_csrf_token_12345"

    # Safe GET method allows cookie without CSRF header
    get_request = MagicMock()
    get_request.cookies = {COOKIE_ACCESS: token, COOKIE_CSRF: csrf_secret}
    get_request.headers = {}
    get_request.method = "GET"
    assert auth_mgr.authenticate_request(get_request) == "admin"

    # Mutating POST method without CSRF header raises 403 Forbidden
    post_request_no_csrf = MagicMock()
    post_request_no_csrf.cookies = {COOKIE_ACCESS: token, COOKIE_CSRF: csrf_secret}
    post_request_no_csrf.headers = {}
    post_request_no_csrf.method = "POST"
    with pytest.raises(HTTPException) as exc_info:
        auth_mgr.authenticate_request(post_request_no_csrf)
    assert exc_info.value.status_code == 403

    # Mutating POST method with valid CSRF header succeeds
    post_request_with_csrf = MagicMock()
    post_request_with_csrf.cookies = {COOKIE_ACCESS: token, COOKIE_CSRF: csrf_secret}
    post_request_with_csrf.headers = {CSRF_HEADER: csrf_secret}
    post_request_with_csrf.method = "POST"
    assert auth_mgr.authenticate_request(post_request_with_csrf) == "admin"
