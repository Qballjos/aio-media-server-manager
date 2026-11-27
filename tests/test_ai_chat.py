"""Focused coverage for provider routing and keeping provider keys server-side."""

import json
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import ai_assistant
from core import ai_chat
from core.crypto import SecretStore


def test_provider_key_and_optional_live_status(monkeypatch, tmp_path):
    app = FastAPI()
    app.include_router(ai_assistant.router)
    client = TestClient(app)
    path = "/api/ai-assistant"
    assert client.get(path + "/providers").status_code == 401
    app.dependency_overrides[ai_assistant._require_manager] = lambda: None
    monkeypatch.setattr(ai_assistant, "secret_store", SecretStore(
        key_path=tmp_path / "key", storage_path=tmp_path / "secrets",
    ))
    complete = AsyncMock(return_value="OK")
    monkeypatch.setattr(ai_assistant, "complete", complete)
    health = AsyncMock(return_value='[{"service":"sonarr","ok":true}]')
    monkeypatch.setattr(ai_assistant, "stack_health", health)
    endpoint = "http://192.168.2.82:6060/mcp"
    assert client.put(path + "/arr-mcp/settings", json={"endpoint": endpoint, "token": "read-token"}).is_success
    response = client.put(path + "/providers/claude", json={"model": "claude-test", "api_key": "a-secret"})
    assert response.json() == {"model": "claude-test"}
    assert client.get(path + "/providers").json() == {"claude": "claude-test"}
    messages = [{"role": "user", "content": "Is Sonarr up?"}]
    assert client.post(path + "/chat", json={"provider": "claude", "messages": messages}).json() == {"reply": "OK"}
    health.assert_not_awaited()
    complete.assert_awaited_once_with("claude", "a-secret", "claude-test", messages, "")
    response = client.post(path + "/chat", json={"provider": "claude", "messages": messages, "include_health": True})
    assert response.json() == {"reply": "OK"}
    health.assert_awaited_once_with(endpoint, "read-token")
    assert complete.await_args.args[-1] == health.return_value


@pytest.mark.asyncio
@pytest.mark.parametrize(("provider", "url", "response"), [
    ("openai", "https://api.openai.com/v1/chat/completions", {"choices": [{"message": {"content": "OK"}}]}),
    ("claude", "https://api.anthropic.com/v1/messages", {"content": [{"type": "text", "text": "OK"}]}),
    ("gemini", "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
     {"choices": [{"message": {"content": "OK"}}]}),
])
async def test_provider_request(monkeypatch, provider, url, response):
    real_client = httpx.AsyncClient

    def handler(request):
        assert str(request.url) == url
        assert request.headers["Authorization"] == "Bearer fixture-key"
        body = json.loads(request.content)
        assert body["messages"][-1] == {"role": "user", "content": "Hello"}
        if provider == "claude":
            assert "anthropic-version" in request.headers
            assert "system" in body
        else:
            assert body["messages"][0]["role"] == "system"
        return httpx.Response(200, json=response)

    monkeypatch.setattr(
        ai_chat.httpx, "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    assert await ai_chat.complete(provider, "fixture-key", "fixture-model", [{"role": "user", "content": "Hello"}]) == "OK"


@pytest.mark.asyncio
async def test_download_action_requires_preview_confirmation(monkeypatch):
    from core import ai_arr_mcp

    request = AsyncMock(side_effect=[
        {"structuredContent": {"summary": "Pause downloads", "applied": False, "confirm_token": "v2.fixture"}},
        {"structuredContent": {"summary": "Downloads paused", "applied": True}},
    ])
    monkeypatch.setattr(ai_arr_mcp, "_request", request)
    endpoint = "http://192.168.2.82:6060/mcp"
    preview = await ai_arr_mcp.change_downloads(endpoint, "mcp-token", "qbittorrent", "pause", None)
    assert preview == {"summary": "Pause downloads", "confirm": "v2.fixture", "applied": False}
    assert request.await_args.args[2]["params"]["arguments"] == {"action": "pause", "service": "qbittorrent"}
    result = await ai_arr_mcp.change_downloads(endpoint, "mcp-token", "qbittorrent", "pause", preview["confirm"])
    assert result == {"summary": "Downloads paused", "confirm": None, "applied": True}
    assert request.await_args.args[2]["params"]["arguments"]["confirm"] == "v2.fixture"
