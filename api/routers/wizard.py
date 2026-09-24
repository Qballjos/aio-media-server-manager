"""api/routers/wizard.py — Guided 12-Step Setup Wizard API Endpoints."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status

from core.wizard import wizard_engine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/wizard", tags=["Wizard"])


@router.get("/status", summary="Get wizard completion status and current step")
async def get_wizard_status() -> dict[str, Any]:
    return await asyncio.to_thread(wizard_engine.get_status)


@router.get("/step/{step_id}", summary="Get configuration schema and data for a wizard step")
async def get_wizard_step(step_id: int) -> dict[str, Any]:
    if step_id < 1 or step_id > 12:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Step ID must be between 1 and 12")
    return await asyncio.to_thread(wizard_engine.get_step_data, step_id)


@router.post("/step/{step_id}", summary="Submit selections for a wizard step")
async def submit_wizard_step(step_id: int, request: Request) -> dict[str, Any]:
    if step_id < 1 or step_id > 12:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Step ID must be between 1 and 12")
    try:
        data = await request.json()
        if not isinstance(data, dict):
            data = {}
    except Exception:
        data = {}
    return await asyncio.to_thread(wizard_engine.update_step_selections, step_id, data)


@router.post("/skip", summary="Skip remaining wizard steps and open the dashboard")
async def skip_wizard() -> dict[str, Any]:
    return await asyncio.to_thread(wizard_engine.skip)


@router.post("/execute", summary="Execute wizard installation and automatic wiring")
async def execute_wizard() -> dict[str, Any]:
    return await wizard_engine.execute_installation()
