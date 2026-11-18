"""
tests/test_auth.py — Unit tests for authentication, password hashing, JWT sessions, and CSRF protection.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from core import two_factor
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
    auth_mgr.create_admin("admin", "AdminPassword123!", email="admin@example.com")
    assert auth_mgr.setup_required() is False
    assert auth_mgr.username() == "admin"
    assert auth_mgr.email() == "admin@example.com"

    # Verifying password
    assert auth_mgr.verify_password("admin", "AdminPassword123!") is True
    assert auth_mgr.verify_password("admin", "WrongPassword!") is False
    assert auth_mgr.verify_password("other_user", "AdminPassword123!") is False

    # Second setup should fail with 409 Conflict
    with pytest.raises(HTTPException) as exc_info:
        auth_mgr.create_admin("admin2", "AdminPassword123!")
    assert exc_info.value.status_code == 409


def test_update_account_stores_names(auth_mgr: AuthManager):
    auth_mgr.create_admin("admin", "AdminPassword123!", email="admin@example.com")
    updated = auth_mgr.update_account(
        "admin",
        current_password="AdminPassword123!",
        first_name="  Jozef  ",
        last_name="Ball",
    )
    assert updated["first_name"] == "Jozef"
    assert updated["last_name"] == "Ball"
    assert auth_mgr.first_name() == "Jozef"
    assert auth_mgr.last_name() == "Ball"
    cleared = auth_mgr.update_account(
        "admin",
        current_password="AdminPassword123!",
        first_name="   ",
        last_name="",
    )
    assert cleared["first_name"] == ""
    assert cleared["last_name"] == ""


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


def test_bearer_skips_csrf_when_session_cookie_also_present(auth_mgr: AuthManager):
    """After a browser refresh the SPA still sends the httponly cookie plus Bearer."""
    token = auth_mgr.issue_token("admin")
    request = MagicMock()
    request.cookies = {COOKIE_ACCESS: token, COOKIE_CSRF: "stale-or-unread"}
    request.headers = {"Authorization": f"Bearer {token}"}
    request.method = "POST"
    assert auth_mgr.authenticate_request(request) == "admin"


@pytest.mark.parametrize(("timestamp", "code"), [(59, "287082"), (1111111109, "081804")])
def test_totp_rfc6238_sha1_vectors(timestamp: int, code: str):
    # Appendix B sample key, with the published result reduced to six digits.
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
    assert two_factor.totp_code(secret, timestamp // 30) == code


def test_member_session_is_rejected_by_admin_authentication(auth_mgr: AuthManager):
    auth_mgr.media_users.grant("plex", "server-a", "42")
    token = auth_mgr.issue_member_token("plex", "server-a", "42")
    request = MagicMock()
    request.headers = {"Authorization": f"Bearer {token}"}
    request.cookies = {}
    request.method = "GET"

    assert auth_mgr.authenticate_member_request(request) == "42"
    with pytest.raises(HTTPException) as admin_error:
        auth_mgr.authenticate_request(request)
    assert admin_error.value.status_code == 403
    with pytest.raises(HTTPException):
        auth_mgr.decode_token(token)

    auth_mgr.revoke_request_session(request, member=True)
    with pytest.raises(HTTPException) as revoked_error:
        auth_mgr.authenticate_member_request(request)
    assert revoked_error.value.status_code == 401


def test_admin_session_is_rejected_by_member_authentication(auth_mgr: AuthManager):
    request = MagicMock()
    request.headers = {"Authorization": f"Bearer {auth_mgr.issue_token('admin')}"}
    request.cookies = {}
    request.method = "GET"

    with pytest.raises(HTTPException) as error:
        auth_mgr.authenticate_member_request(request)
    assert error.value.status_code == 403


def test_member_library_credential_stays_in_the_server_session(auth_mgr):
    auth_mgr.media_users.grant("jellyfin", "server-a", "42")
    credential = "provider-library-credential"
    token = auth_mgr.issue_member_token("jellyfin", "server-a", "42", library_token=credential)
    payload = auth_mgr.decode_token(token, member=True)
    assert credential not in str(payload)
    directory = auth_mgr.media_users.path.parent / ".sessions"
    assert credential.encode() not in (directory / payload["jti"]).read_bytes()
    request = MagicMock()
    request.headers = {"Authorization": f"Bearer {token}"}
    request.method = "GET"
    assert auth_mgr.member_library_token(request) == credential
    auth_mgr.media_users.revoke("jellyfin", "server-a", "42")
    with pytest.raises(HTTPException) as error:
        auth_mgr.member_library_token(request)
    assert error.value.status_code == 401
