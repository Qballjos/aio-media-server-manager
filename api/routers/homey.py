"""Homey pairing, revocation and strictly read-only dashboard data."""

import asyncio
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from core.auth import auth_manager
from core.homey_dashboard import dashboard

router = APIRouter(prefix="/api/homey", tags=["Homey"])


class Claim(BaseModel):
    code: str = Field(min_length=32, max_length=100)
    deviceName: str = Field(
        default="Homey", min_length=1, max_length=80, pattern=r"^[^\x00-\x1f\x7f]+$"
    )


def admin(request):
    identity = auth_manager.authenticate_request(request)
    if identity.startswith(("tv:", "homey:")):
        raise HTTPException(403, "Administrator access required.")


@router.post("/pairings")
def invite(request: Request, response: Response):
    admin(request)
    response.headers["Cache-Control"] = "no-store"
    return auth_manager.homey_connections.invite()


@router.post("/pairings/claim")
def claim(body: Claim, request: Request, response: Response):
    if auth_manager.setup_required():
        raise HTTPException(403, "Set up the administrator before pairing Homey.")
    auth_manager.check_login_rate(request)
    response.headers["Cache-Control"] = "no-store"
    return auth_manager.homey_connections.claim(body.code, body.deviceName)


@router.get("/devices")
def devices(request: Request):
    admin(request)
    return {"devices": auth_manager.homey_connections.devices()}


@router.delete("/devices/{device_id}")
def revoke(device_id: str, request: Request):
    admin(request)
    auth_manager.homey_connections.revoke(device_id)
    return {"ok": True}


@router.post("/disconnect")
def disconnect(request: Request):
    identity = auth_manager.authenticate_request(request)
    if not identity.startswith("homey:"):
        raise HTTPException(400, "Use the connection list to disconnect Homey.")
    auth_manager.homey_connections.revoke(identity[6:])
    return {"ok": True}


@router.get("/dashboard")
async def get_dashboard(request: Request, response: Response):
    auth_manager.authenticate_request(request)
    response.headers["Cache-Control"] = "no-store"
    return await asyncio.to_thread(dashboard)
