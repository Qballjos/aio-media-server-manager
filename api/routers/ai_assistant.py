"""Administrator settings for an external, local arr-mcp service."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, SecretStr

from api.routers.auth import AuthRoute
from core.ai_arr_mcp import ArrMcpError, check_connection, local_endpoint
from core.auth import auth_manager
from core.crypto import secret_store

_ARR_MCP_SECRET = "ai_arr_mcp_settings"


def _require_manager(request: Request) -> None:
    auth_manager.authenticate_request(request)
    if not getattr(request.state, "manager_session_id", None):
        raise HTTPException(403, "A manager session is required.")


router = APIRouter(
    prefix="/api/ai-assistant", tags=["External AI connection"],
    dependencies=[Depends(_require_manager)], route_class=AuthRoute,
)


class ArrMcpConfiguration(BaseModel):
    chat_url: str = Field(min_length=1, max_length=256)
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
        chat_url = local_endpoint(body.chat_url.strip(), mcp=False)
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
        raise HTTPException(422, "Enter a valid arr-mcp read token.")
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
