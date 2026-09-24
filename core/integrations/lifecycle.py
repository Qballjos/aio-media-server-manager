"""Start an app after install and run wiring once it is actually reachable."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import requests

from applications.base import BaseApplication
from core.integrations.credentials import wait_for_application_api_key
from core.integrations.engine import WIRE_AFTER_INSTALL, integration_engine
from core.settings import settings
from core.supervisor import ProcessSupervisor
from core.vpn import VPN_TUNNELED_APPS, VpnIsolationError, vpn_manager

logger = logging.getLogger(__name__)

_wiring_lock = asyncio.Lock()
_pending_wiring = 0


async def schedule_full_wiring() -> dict[str, Any]:
    """Coalesce overlapping wiring requests so the event loop stays free."""
    global _pending_wiring
    _pending_wiring += 1
    async with _wiring_lock:
        if _pending_wiring == 0:
            return {"status": "coalesced"}
        _pending_wiring = 0
        return await asyncio.to_thread(integration_engine.run_full_wiring)


async def finalize_application_install(plugin: BaseApplication) -> dict[str, Any]:
    """Start a newly installed daemon, wait until it answers, then wire."""
    report: dict[str, Any] = {"name": plugin.name, "started": False, "wired": False}
    if plugin.manifest.daemon:
        supervisor = ProcessSupervisor.get()
        log_dir = settings.config_dir / "logs"
        try:
            if plugin.name in VPN_TUNNELED_APPS:
                vpn_manager.assert_can_start_tunneled_app(plugin.name)
            await supervisor.start(
                name=plugin.name,
                cmd=plugin.start_command(),
                cwd=plugin.working_directory(),
                env=plugin.extra_env(),
                log_dir=log_dir,
            )
            report["started"] = True
        except (RuntimeError, VpnIsolationError) as exc:
            logger.info("Did not start '%s' after install: %s", plugin.name, exc)
            report["start_error"] = str(exc)

        healthy = await _wait_healthy(plugin)
        report["healthy"] = healthy
        if healthy:
            key = await wait_for_application_api_key(plugin.name, timeout=90.0)
            report["has_api_key"] = bool(key)
        else:
            logger.warning(
                "Health check timed out for '%s'; wiring will skip it until it is running.",
                plugin.name,
            )

    if plugin.name not in WIRE_AFTER_INSTALL:
        return report

    logger.info("Running integration wiring after '%s' install.", plugin.name)
    try:
        report["wiring"] = await schedule_full_wiring()
        report["wired"] = True
    except Exception as exc:
        logger.error("Wiring after '%s' failed: %s", plugin.name, exc, exc_info=True)
        report["wiring_error"] = str(exc)
    return report


async def _wait_healthy(plugin: BaseApplication, timeout: float = 90.0) -> bool:
    url = plugin.health_check_url()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            resp = await asyncio.to_thread(requests.get, url, timeout=2.0)
            if resp.status_code < 500:
                return True
        except Exception:
            pass
        await asyncio.sleep(1.5)
    return False
