"""Pasting a Cloudflare API token, and explaining Cloudflare's 'Invalid request headers'."""

import pytest

from core import cloudflare_api
from core.cloudflare_api import CloudflareApiError, _format_cloudflare_api_error, _normalize_api_token

TOKEN = "Abc123_def456-GHI789jkl012MNO345pqr678st"  # 40 chars, the shape Cloudflare issues


def test_pasted_token_loses_quotes_bearer_and_line_breaks():
    assert _normalize_api_token(f'"Bearer {TOKEN[:20]}\n  {TOKEN[20:]}"') == TOKEN
    assert _normalize_api_token(f"​{TOKEN} ") == TOKEN


def test_an_id_is_refused_as_api_token(monkeypatch):
    saved = {}
    monkeypatch.setattr(cloudflare_api.secret_store, "save_secret", lambda k, v: saved.update({k: v}))
    with pytest.raises(CloudflareApiError, match="account, zone or tunnel ID"):
        cloudflare_api.set_api_token("0123456789abcdef0123456789abcdef")
    assert not saved


def test_invalid_request_headers_gets_a_clear_message():
    errors = [{"code": 6003, "message": "Invalid request headers", "error_chain": [{"code": 6111, "message": "Invalid format for Authorization header"}]}]
    msg = _format_cloudflare_api_error(errors, 400)
    assert "not an API token" in msg and "My Profile → API Tokens" in msg
