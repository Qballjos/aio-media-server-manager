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


async def schedule_full_wiring(*, wait_for_apps: bool = False) -> dict[str, Any]:
    """Coalesce overlapping wiring requests so the event loop stays free."""
    global _pending_wiring
    _pending_wiring += 1
    async with _wiring_lock:
        if _pending_wiring == 0:
            return {"status": "coalesced"}
        _pending_wiring = 0
        if wait_for_apps:
            await _wait_wiring_prereqs()
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

    if not plugin.manifest.daemon and plugin.name not in WIRE_AFTER_INSTALL:
        return report

    logger.info("Running integration wiring after '%s' install.", plugin.name)
    try:
        report["wiring"] = await schedule_full_wiring()
        report["wired"] = True
    except Exception as exc:
        logger.error("Wiring after '%s' failed: %s", plugin.name, exc, exc_info=True)
        report["wiring_error"] = str(exc)
    return report


def _reclaim_tunneled_command(cmd: list[str]) -> list[str]:
    """Strip setpriv / netns / env wrappers so leftover host-network copies still match."""
    from core.vpn import unwrap_isolation_command

    return unwrap_isolation_command(cmd)


async def stop_tunneled_apps() -> list[str]:
    """Stop qBittorrent, Prowlarr, and Flaresolverr so they cannot leak on the house WAN."""
    from applications.catalog import ApplicationCatalog
    from core.supervisor import reclaim_leftover_processes

    catalog = ApplicationCatalog()
    supervisor = ProcessSupervisor.get()
    stopped: list[str] = []
    for name in sorted(VPN_TUNNELED_APPS):
        state = supervisor.status(name)
        value = getattr(state, "value", state)
        if value == "running":
            try:
                await supervisor.stop(name)
                stopped.append(name)
            except Exception as exc:
                logger.warning("Could not stop tunneled app %s: %s", name, exc)
        if not catalog.has(name):
            continue
        plugin = catalog.get(name)
        if not plugin.is_installed():
            continue
        try:
            cmd = plugin.start_command()
        except Exception:
            continue
        killed = reclaim_leftover_processes(cmd)
        killed += reclaim_leftover_processes(_reclaim_tunneled_command(cmd))
        if killed and name not in stopped:
            stopped.append(name)
    return stopped


async def enforce_vpn_isolation() -> list[str]:
    """If VPN is on without a tunnel, stop qBittorrent/Prowlarr/Flaresolverr."""
    if vpn_manager.tunneled_apps_allowed():
        # Keep WebUI proxies alive while the tunnel is up (Docker may race start).
        try:
            vpn_manager.refresh_local_forwards()
        except Exception as exc:
            logger.debug("VPN WebUI forward refresh failed: %s", exc)
        # Kill any leftover clearnet copies that bypass WireGuard UID routing.
        try:
            leaked = vpn_manager.reclaim_clearnet_tunneled_processes()
        except Exception as exc:
            logger.warning("Clearnet tunneled-process reclaim failed: %s", exc)
            leaked = []
        if leaked:
            restarted = await start_tunneled_apps(leaked)
            if restarted:
                logger.warning(
                    "Restarted %s under VPN isolation after clearing a house-network process.",
                    ", ".join(restarted),
                )
            return leaked
        return []
    stopped = await stop_tunneled_apps()
    if stopped:
        logger.error(
            "Stopped %s because VPN is enabled but the tunnel is down.",
            ", ".join(stopped),
        )
    return stopped


async def vpn_isolation_loop(interval: float = 5.0) -> None:
    """Keep tunneled apps off the house WAN if the tunnel drops after they started."""
    while True:
        try:
            await enforce_vpn_isolation()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("VPN isolation check failed: %s", exc)
        await asyncio.sleep(interval)


async def start_tunneled_apps(names: list[str] | None = None) -> list[str]:
    """Start tunneled apps only when the VPN namespace has a live tunnel (or VPN is off)."""
    from applications.catalog import ApplicationCatalog

    catalog = ApplicationCatalog()
    supervisor = ProcessSupervisor.get()
    log_dir = settings.config_dir / "logs"
    wanted = set(names) if names is not None else set(VPN_TUNNELED_APPS)
    started: list[str] = []
    for name in sorted(wanted):
        if name not in VPN_TUNNELED_APPS:
            continue
        if not catalog.has(name):
            continue
        plugin = catalog.get(name)
        if not plugin.manifest.daemon or not plugin.is_installed():
            continue
        try:
            vpn_manager.assert_can_start_tunneled_app(name)
        except VpnIsolationError as exc:
            logger.info("Leaving '%s' stopped: %s", name, exc)
            continue
        try:
            await supervisor.start(
                name=name,
                cmd=plugin.start_command(),
                cwd=plugin.working_directory(),
                env=plugin.extra_env(),
                log_dir=log_dir,
            )
            started.append(name)
        except Exception as exc:
            logger.warning("Could not start tunneled app %s: %s", name, exc)
    return started


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


async def _wait_wiring_prereqs(timeout: float = 90.0) -> None:
    """Give *Arr and download clients time to write API keys after autostart."""
    from applications.catalog import ApplicationCatalog
    from core.integrations.credentials import APPS_WITH_FILE_API_KEYS, get_application_api_key

    catalog = ApplicationCatalog()
    names = [
        plugin.name
        for plugin in catalog.all_plugins()
        if plugin.manifest.daemon and plugin.is_installed() and plugin.name in WIRE_AFTER_INSTALL
    ]
    if not names:
        return
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        ready = True
        for name in names:
            plugin = catalog.get(name)
            if not await _probe_url(plugin.health_check_url()):
                ready = False
                break
            if name in APPS_WITH_FILE_API_KEYS and not get_application_api_key(name):
                ready = False
                break
        if ready:
            return
        await asyncio.sleep(1.5)


async def _probe_url(url: str) -> bool:
    try:
        resp = await asyncio.to_thread(requests.get, url, timeout=2.0)
        return resp.status_code < 500
    except Exception:
        return False


async def bring_up_vpn(manager: Any = None) -> dict[str, Any]:
    """Bring the tunnel up, then run every installed tunneled app on it.

    Shared by the wizard, Settings → Network, and POST /api/vpn/start so they
    behave the same. Nothing may have been running yet (fresh install), so a
    tunnel that comes up starts all tunneled apps, not just the ones stopped here.
    """
    manager = manager or vpn_manager
    stopped = await stop_tunneled_apps()
    result = await asyncio.to_thread(manager.start)
    if result.get("tunnel_up"):
        result["started_apps"] = await start_tunneled_apps(stopped or None)
        if result["started_apps"]:
            # Apps that only start once the tunnel is up still need their shared
            # login and *Arr links; the install-time wiring skipped them.
            asyncio.create_task(schedule_full_wiring(wait_for_apps=True))
    else:
        await enforce_vpn_isolation()
        result["started_apps"] = []
    return result
