"""Settings → Notifications: Discord and e-mail for the manager's own events."""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from core import notifications as notifications_mod
from core.auth import auth_manager

router = APIRouter(prefix="/api/notifications", tags=["Notifications"])


class DiscordBody(BaseModel):
    enabled: bool = False
    webhook_url: str | None = Field(default=None, max_length=300)  # None keeps the saved one, "" removes it


class EmailBody(BaseModel):
    enabled: bool = False
    host: str = Field(default="", max_length=253)
    port: int = Field(default=587, ge=1, le=65535)
    security: Literal["starttls", "ssl", "none"] = "starttls"
    username: str = Field(default="", max_length=200)
    password: str | None = Field(default=None, max_length=300)  # None keeps the saved one, "" removes it
    sender: str = Field(default="", max_length=200)
    recipients: str = Field(default="", max_length=2000)


class NotificationsBody(BaseModel):
    discord: DiscordBody = DiscordBody()
    email: EmailBody = EmailBody()
    events: dict[str, bool] = {}


class TestBody(BaseModel):
    channel: Literal["discord", "email"]


@router.get("", summary="Notification channels and events")
async def get_notifications(request: Request) -> dict[str, Any]:
    auth_manager.authenticate_request(request)
    return notifications_mod.public_config()


@router.put("", summary="Save notification channels and events")
async def put_notifications(body: NotificationsBody, request: Request) -> dict[str, Any]:
    auth_manager.authenticate_request(request)
    email = body.email.model_dump()
    password = email.pop("password")
    try:
        return notifications_mod.save_config(
            discord_enabled=body.discord.enabled,
            webhook_url=body.discord.webhook_url,
            email=email,
            smtp_password=password,
            events=body.events,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/test", summary="Send a test notification to one channel")
async def test_notification(body: TestBody, request: Request) -> dict[str, Any]:
    auth_manager.authenticate_request(request)
    try:
        await asyncio.to_thread(notifications_mod.send_test, body.channel)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Could not send: {exc}") from exc
    return {"ok": True}
