"""Pair a launcher without exporting administrator or Jellyfin credentials."""

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field

from core.auth import auth_manager

router = APIRouter(prefix="/api/tv", tags=["TV pairing"])


class Claim(BaseModel):
    code: str = Field(min_length=32, max_length=100)
    deviceName: str = Field(
        default="TV Thuis", min_length=1, max_length=80, pattern=r"^[^\x00-\x1f\x7f]+$"
    )


@router.post("/pairings")
def invite(request: Request):
    auth_manager.authenticate_request(request)
    return auth_manager.tv_devices.invite()


@router.post("/pairings/claim")
def claim(body: Claim, request: Request):
    if auth_manager.setup_required():
        raise HTTPException(403, "Set up the administrator before pairing a TV.")
    auth_manager.check_login_rate(request)
    return auth_manager.tv_devices.claim(body.code, body.deviceName)


@router.post("/disconnect")
def disconnect(request: Request):
    identity = auth_manager.authenticate_request(request)
    if not identity.startswith("tv:"):
        raise HTTPException(400, "Use the device list to disconnect a TV.")
    auth_manager.tv_devices.revoke(identity[3:])
    return {"ok": True}


@router.get("/devices")
def devices(request: Request):
    auth_manager.authenticate_request(request)
    return {"devices": auth_manager.tv_devices.devices()}


@router.delete("/devices/{device_id}")
def revoke(device_id: str, request: Request):
    auth_manager.authenticate_request(request)
    auth_manager.tv_devices.revoke(device_id)
    return {"ok": True}
