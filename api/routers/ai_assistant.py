"""Administrator-only AI chat and local arr-mcp settings."""

from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, SecretStr

from api.routers.auth import AuthRoute
from core.ai_arr_mcp import ArrMcpError, change_downloads, check_connection, local_endpoint, stack_health
from core.ai_chat import AiChatError, complete
from core.auth import auth_manager
from core.crypto import secret_store

_ARR_MCP_SECRET = "ai_arr_mcp_settings"
_CHAT_PREFERENCES = "ai_chat_preferences"


def _require_manager(request: Request) -> None:
    auth_manager.authenticate_request(request)
    if not getattr(request.state, "manager_session_id", None):
        raise HTTPException(403, "A manager session is required.")


router = APIRouter(
    prefix="/api/ai-assistant", tags=["AI assistant"],
    dependencies=[Depends(_require_manager)], route_class=AuthRoute,
)


class ArrMcpConfiguration(BaseModel):
    chat_url: str | None = Field(default=None, min_length=1, max_length=256)
    endpoint: str | None = Field(default=None, max_length=128)
    token: SecretStr | None = None


def _arr_mcp_configuration() -> dict | None:
    value = secret_store.get_secret(_ARR_MCP_SECRET)
    return json.loads(value) if value else None


@router.get("/arr-mcp/settings")
def arr_mcp_settings() -> dict:
    config = _arr_mcp_configuration()
    return {"endpoint": (config or {}).get("endpoint"), "chat_url": (config or {}).get("chat_url")}


@router.put("/arr-mcp/settings")
def save_arr_mcp_settings(body: ArrMcpConfiguration) -> dict:
    try:
        chat_url = local_endpoint(body.chat_url.strip(), mcp=False) if body.chat_url else None
        endpoint = local_endpoint(body.endpoint.strip()) if body.endpoint and body.endpoint.strip() else None
    except ArrMcpError as exc:
        raise HTTPException(422, str(exc)) from None
    token = body.token.get_secret_value().strip() if body.token else ""
    previous = _arr_mcp_configuration()
    if not token and previous and previous["endpoint"] == endpoint:
        token = previous["token"]
    if endpoint and (not token or len(token) > 2048 or not token.isascii() or not all(
        character.isprintable() and not character.isspace() for character in token
    )):
        raise HTTPException(422, "Enter a valid arr-mcp token.")
    secret_store.save_secret(_ARR_MCP_SECRET, json.dumps({
        "chat_url": chat_url, "endpoint": endpoint, "token": token if endpoint else "",
    }))
    return {"endpoint": endpoint, "chat_url": chat_url}


@router.delete("/arr-mcp/settings", status_code=204)
def disconnect_arr_mcp() -> Response:
    secret_store.delete_secret(_ARR_MCP_SECRET)
    return Response(status_code=204)


@router.post("/arr-mcp/check")
async def check_arr_mcp() -> dict:
    config = _arr_mcp_configuration()
    if not config or not config.get("endpoint"):
        raise HTTPException(409, "Configure arr-mcp first.")
    try:
        await check_connection(config["endpoint"], config["token"])
    except ArrMcpError as exc:
        raise HTTPException(502, str(exc)) from None
    return {"connected": True}


Provider = Literal["openai", "claude", "gemini"]


class ProviderConfiguration(BaseModel):
    model: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
    api_key: SecretStr | None = None


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=16000)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=9)


def _provider_config(provider: Provider) -> dict | None:
    config = secret_store.get_secret(f"ai_chat_{provider}")
    return json.loads(config) if config else None


@router.get("/providers")
def list_providers() -> dict:
    providers = {}
    for provider in ("openai", "claude", "gemini"):
        if config := _provider_config(provider):
            providers[provider] = config["model"]
    return providers


class ChatPreferences(BaseModel):
    provider: Provider | None = None
    share_local_status: bool = False


@router.get("/preferences")
def chat_preferences() -> ChatPreferences:
    raw = secret_store.get_secret(_CHAT_PREFERENCES)
    if raw:
        preferences = ChatPreferences.model_validate_json(raw)
        if preferences.provider and not _provider_config(preferences.provider):
            return ChatPreferences()
        return preferences
    configured = list(list_providers())
    return ChatPreferences(provider=configured[0] if len(configured) == 1 else None)


@router.put("/preferences")
def save_chat_preferences(body: ChatPreferences) -> ChatPreferences:
    if body.provider and not _provider_config(body.provider):
        raise HTTPException(409, "Configure this AI provider first.")
    secret_store.save_secret(_CHAT_PREFERENCES, body.model_dump_json())
    return body


@router.put("/providers/{provider}")
def save_provider(provider: Provider, body: ProviderConfiguration) -> dict:
    if body.api_key is None:
        key = (_provider_config(provider) or {}).get("key", "")
    else:
        key = body.api_key.get_secret_value().strip()
    if not key or len(key) > 2048 or not all(33 <= ord(character) <= 126 for character in key):
        raise HTTPException(422, "Enter a valid provider API key.")
    secret_store.save_secret(f"ai_chat_{provider}", json.dumps({"model": body.model, "key": key}))
    return {"model": body.model}


@router.delete("/providers/{provider}", status_code=204)
def remove_provider(provider: Provider) -> Response:
    secret_store.delete_secret(f"ai_chat_{provider}")
    return Response(status_code=204)


@router.post("/chat")
async def send_chat(body: ChatRequest) -> dict:
    preferences = chat_preferences()
    provider = preferences.provider
    config = _provider_config(provider) if provider else None
    if not config:
        raise HTTPException(409, "Configure this AI provider first.")
    if (
        len(body.messages) % 2 != 1
        or any(message.role != ("assistant" if i % 2 else "user") for i, message in enumerate(body.messages))
        or not body.messages[-1].content.strip()
        or sum(len(message.content) for message in body.messages) > 24000
    ):
        raise HTTPException(422, "The chat history is invalid or too long. Start a new chat.")
    health = ""
    if preferences.share_local_status:
        mcp = _arr_mcp_configuration()
        if mcp and mcp.get("endpoint"):
            try:
                health = await stack_health(mcp["endpoint"], mcp["token"])
            except ArrMcpError:
                health = ""
    try:
        reply = await complete(
            provider, config["key"], config["model"],
            [message.model_dump() for message in body.messages], health,
        )
    except AiChatError as exc:
        raise HTTPException(502, str(exc)) from None
    return {"reply": reply}

class DownloadAction(BaseModel):
    service: Literal["qbittorrent", "sabnzbd", "nzbget", "transmission"]
    action: Literal["pause", "resume"]
    confirm: SecretStr | None = None


@router.post("/arr-mcp/downloads")
async def change_mcp_downloads(body: DownloadAction) -> dict:
    config = _arr_mcp_configuration()
    if not config or not config.get("endpoint"):
        raise HTTPException(409, "Configure arr-mcp first.")
    confirm = body.confirm.get_secret_value() if body.confirm else None
    if confirm is not None and (not confirm or len(confirm) > 256):
        raise HTTPException(422, "Request a new preview.")
    try:
        return await change_downloads(config["endpoint"], config["token"], body.service, body.action, confirm)
    except ArrMcpError as exc:
        raise HTTPException(502, str(exc)) from None
