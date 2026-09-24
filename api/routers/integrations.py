"""
api/routers/integrations.py — Automatic Integration Engine API Endpoints.

Provides endpoints to inspect connectivity and trigger automatic inter-application wiring.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Request

from core.auth import auth_manager
from core.integrations.engine import integration_engine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/integrations", tags=["Integrations"])


def _ensure_authenticated(request: Request) -> None:
    if not auth_manager.setup_required():
        auth_manager.authenticate_request(request)


@router.get("/status", summary="Inspect application integration and wiring status")
async def get_integration_status(request: Request) -> dict[str, Any]:
    """
    Returns detected API keys, running statuses, and wiring readiness.
    """
    _ensure_authenticated(request)
    status_report = integration_engine.get_wiring_status()
    return {"integrations": status_report}


@router.post("/run", summary="Trigger automatic inter-application wiring")
async def run_integration_wiring(request: Request) -> dict[str, Any]:
    """
    Executes automatic category setup, download client registration, indexer synchronization,
    and media server linking.
    """
    _ensure_authenticated(request)
    return await asyncio.to_thread(integration_engine.run_full_wiring)
