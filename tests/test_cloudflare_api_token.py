"""Pasting a Cloudflare API token, and explaining Cloudflare's 'Invalid request headers'."""

from types import SimpleNamespace

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


def test_a_value_that_is_not_a_token_never_replaces_the_saved_one(monkeypatch):
    saved = {"cloudflare_api_token": "working-token"}
    monkeypatch.setattr(cloudflare_api.secret_store, "save_secret", lambda k, v: saved.update({k: v}))
    # Checked locally: a password a browser filled in must not be sent anywhere.
    monkeypatch.setattr(cloudflare_api.httpx, "AsyncClient", lambda **kw: pytest.fail("no network call"))
    for not_a_token in ("Hunter2!pass", "short_but_clean_token", TOKEN[:39], TOKEN[:20] + "!" + TOKEN[21:]):
        with pytest.raises(CloudflareApiError, match="not saved"):
            cloudflare_api.set_api_token(not_a_token)
    assert saved["cloudflare_api_token"] == "working-token"
    cloudflare_api.set_api_token(TOKEN)
    assert saved["cloudflare_api_token"] == TOKEN
    cloudflare_api.set_api_token("cfut_" + TOKEN + "ABCDEFGH")  # longer formats are fine
