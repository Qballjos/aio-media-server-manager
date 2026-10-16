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


class _FakeClient:
    def __init__(self, answer):
        self.answer = answer

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, headers):
        if isinstance(self.answer, Exception):
            raise self.answer
        return SimpleNamespace(json=lambda: self.answer)


def test_a_value_cloudflare_calls_no_token_never_replaces_the_saved_one(monkeypatch):
    import asyncio
    import httpx

    saved = {"cloudflare_api_token": "working-token"}
    monkeypatch.setattr(cloudflare_api.secret_store, "save_secret", lambda k, v: saved.update({k: v}))

    def put(value, answer):
        monkeypatch.setattr(cloudflare_api.httpx, "AsyncClient", lambda **kw: _FakeClient(answer))

        async def run():
            await cloudflare_api.refuse_malformed_api_token(value)
            cloudflare_api.set_api_token(value)

        asyncio.run(run())

    with pytest.raises(CloudflareApiError, match="was not saved"):
        put("my-browser-password", {"success": False, "errors": [{"code": 6003, "message": "Invalid request headers"}]})
    assert saved["cloudflare_api_token"] == "working-token"
    put(TOKEN, {"success": False, "errors": [{"code": 1000, "message": "Invalid API Token"}]})  # account token: allowed
    assert saved["cloudflare_api_token"] == TOKEN
    put(TOKEN[::-1], httpx.ConnectError("offline"))  # no answer: allowed
    assert saved["cloudflare_api_token"] == TOKEN[::-1]
