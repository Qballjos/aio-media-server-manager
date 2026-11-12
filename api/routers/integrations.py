"""
api/routers/integrations.py — Automatic Integration Engine API Endpoints.

Provides endpoints to inspect connectivity and trigger automatic inter-application wiring.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request

from core.auth import auth_manager
from core.integrations.engine import integration_engine
from core.integrations.lifecycle import schedule_full_wiring

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
    return await schedule_full_wiring()


@router.post("/verify", summary="Read back configuration and verify application connections")
async def verify(request: Request) -> dict[str, Any]:
    auth_manager.authenticate_request(request)
    import asyncio
    from core.integration_verify import verify_integrations
    return await asyncio.to_thread(verify_integrations)


@router.get("/public-indexers", summary="Public starter indexer opt-in")
async def get_indexer_choice(request: Request) -> dict[str, Any]:
    auth_manager.authenticate_request(request)
    from core.app_prefs import load_prefs
    from core.integrations.prowlarr import STARTER_INDEXERS
    options = (load_prefs().get("options") or {}).get("prowlarr") or {}
    return {"enabled": options.get("public_indexers_opt_in") is True, "indexers": list(STARTER_INDEXERS)}


from pydantic import BaseModel, StrictBool


class IndexerChoice(BaseModel):
    enabled: StrictBool


@router.put("/public-indexers", summary="Explicitly opt in to public starter indexers")
async def set_indexer_choice(body: IndexerChoice, request: Request) -> dict[str, Any]:
    auth_manager.authenticate_request(request)
    from core.app_prefs import set_app_option
    set_app_option("prowlarr", "public_indexers_opt_in", body.enabled)
    return await get_indexer_choice(request)
