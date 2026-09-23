"""Start an app after install and run *Arr wiring when applicable."""

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


async def finalize_application_install(plugin: BaseApplication) -> dict[str, Any]:
    """Start a newly installed daemon and wire *Arr apps once their API key exists."""
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
        if plugin.name in WIRE_AFTER_INSTALL:
            wait_for_application_api_key(plugin.name, timeout=90.0)

    if plugin.name in WIRE_AFTER_INSTALL:
        logger.info("Running integration wiring after '%s' install.", plugin.name)
        report["wiring"] = integration_engine.run_full_wiring()
        report["wired"] = True
    return report


async def _wait_healthy(plugin: BaseApplication, timeout: float = 90.0) -> bool:
    url = plugin.health_check_url()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            resp = requests.get(url, timeout=2.0)
            if resp.status_code < 500:
                return True
        except Exception:
            pass
        await asyncio.sleep(1.5)
    return False
