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
from core.integrations.local_auth import apply_shared_local_logins
from core.integrations.sessions import SERVARR_APPS
from core.install_jobs import set_job, set_wiring_progress
from core.settings import settings
from core.supervisor import ProcessSupervisor
from core.vpn import VPN_TUNNELED_APPS, VpnIsolationError, vpn_manager

logger = logging.getLogger(__name__)

# After Cloudflare and the VPN. Sonarr, Radarr, and Prowlarr probe these as soon
# as their own process is up and keep a connection-refused warning until the next check.
_BOOT_FIRST = ("flaresolverr", "qbittorrent", "sabnzbd")
_LISTEN_BEFORE_ARR = frozenset(_BOOT_FIRST)
_LISTEN_WAIT_SECONDS = 40.0
_TUNNEL_WAIT_SECONDS = 120.0

_wiring_lock = asyncio.Lock()
_pending_wiring = 0


def boot_autostart_order(names: list[str]) -> list[str]:
    """FlareSolverr, qBittorrent, then SABnzbd, then everyone else in catalog order.

    The VPN starts before this list and Cloudflare after it. Catalog order would
    bring Prowlarr and Sonarr up first and health-check a client that is not listening yet.
    """
    present = set(names)
    first = [name for name in _BOOT_FIRST if name in present]
    rest = [name for name in names if name not in _LISTEN_BEFORE_ARR]
    return first + rest


async def schedule_full_wiring(*, wait_for_apps: bool = False) -> dict[str, Any]:
    """Coalesce overlapping wiring requests so the event loop stays free."""
    global _pending_wiring
    _pending_wiring += 1
    async with _wiring_lock:
        if _pending_wiring == 0:
            return {"status": "coalesced"}
        _pending_wiring = 0
        try:
            set_wiring_progress("Waiting for applications to start" if wait_for_apps else "Preparing application connections")
            if wait_for_apps:
                await _wait_wiring_prereqs()
            return await asyncio.to_thread(integration_engine.run_full_wiring)
        finally:
            set_wiring_progress("")


async def finalize_application_install(plugin: BaseApplication) -> dict[str, Any]:
    """Start a newly installed daemon, wait until it answers, then wire."""
    report: dict[str, Any] = {"name": plugin.name, "started": False, "wired": False}
    if plugin.manifest.daemon:
        set_job(plugin.name, "configuring", "Starting application")
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

        set_job(plugin.name, "configuring", "Waiting for application to respond")
        healthy = await _wait_healthy(plugin)
        report["healthy"] = healthy
        if healthy:
            set_job(plugin.name, "configuring", "Reading connection details")
            key = await wait_for_application_api_key(plugin.name, timeout=90.0)
            report["has_api_key"] = bool(key)
            if plugin.name in SERVARR_APPS:
                set_job(plugin.name, "configuring", "Configuring AIO login")
                login_steps = await asyncio.to_thread(
                    apply_shared_local_logins,
                    installed=lambda name: name == plugin.name,
                    port_for=lambda _name, _fallback: plugin.port,
                    api_key_for=lambda _name: key,
                    config_dir_for=lambda _name: plugin.config_dir,
                )
                report["shared_login"] = bool(login_steps) and all(step["status"] == "success" for step in login_steps)
                # Changing Servarr's auth method restarts the app.
                report["healthy"] = await _wait_healthy(plugin)
        else:
            logger.warning(
                "Health check timed out for '%s'; wiring will skip it until it is running.",
                plugin.name,
            )

    if not plugin.manifest.daemon and plugin.name not in WIRE_AFTER_INSTALL:
        return report

    logger.info("Running integration wiring after '%s' install.", plugin.name)
    try:
        set_job(plugin.name, "configuring", "Waiting for shared setup", wiring=True)
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


# Watchdog state. ponytail: in memory; after a container restart the boot start covers the apps.
_down_checks = 0
_stopped_for_tunnel: set[str] = set()
# Set when a VPN start failed: the watchdog retries it with backoff until the tunnel is up.
_VPN_RETRY_FIRST = 15.0
_VPN_RETRY_MAX = 300.0
_vpn_retry_delay = 0.0
_vpn_retry_at = 0.0
_wire_after_tunnel = False


def hold_for_tunnel(names: list[str] | set[str]) -> None:
    """Start these apps once the tunnel is up, and keep retrying the VPN until it is."""
    global _vpn_retry_delay, _vpn_retry_at, _wire_after_tunnel
    held = {name for name in names if name in VPN_TUNNELED_APPS}
    _stopped_for_tunnel.update(held)
    _wire_after_tunnel = _wire_after_tunnel or bool(held)
    _vpn_retry_delay = _VPN_RETRY_FIRST
    _vpn_retry_at = time.monotonic() + _vpn_retry_delay


def cancel_vpn_retry() -> None:
    """The operator stopped the VPN on purpose; do not bring it back on our own."""
    global _vpn_retry_delay
    _vpn_retry_delay = 0.0


async def _retry_vpn_start() -> bool:
    global _vpn_retry_delay, _vpn_retry_at
    logger.info("VPN tunnel is not up yet; trying to start it again.")
    try:
        result = await asyncio.to_thread(vpn_manager.start)
    except Exception as exc:
        result = {"detail": str(exc)}
    if result.get("tunnel_up"):
        _vpn_retry_delay = 0.0
        return True
    _vpn_retry_delay = min(_vpn_retry_delay * 2, _VPN_RETRY_MAX)
    _vpn_retry_at = time.monotonic() + _vpn_retry_delay
    logger.warning(
        "VPN tunnel still down (%s). %s wait for it; next try in %.0fs.",
        result.get("detail") or result.get("status") or "no handshake",
        ", ".join(sorted(_stopped_for_tunnel)) or "Tunneled apps",
        _vpn_retry_delay,
    )
    return False


async def enforce_vpn_isolation(grace: int = 0) -> list[str]:
    """If VPN is on without a tunnel, stop qBittorrent/Prowlarr/Flaresolverr.

    ``grace`` is how many failed checks in a row to ride out first: the 5 s watchdog passes 2,
    so one slow ``wg show`` on a busy host stops nothing. Apps stopped here start again once
    the tunnel is back.
    """
    global _down_checks, _vpn_retry_delay, _wire_after_tunnel
    # The checks shell out (wg, ip, iptables); keep them off the event loop.
    allowed = await asyncio.to_thread(vpn_manager.tunneled_apps_allowed)
    if not allowed and _vpn_retry_delay and settings.vpn_enabled and time.monotonic() >= _vpn_retry_at:
        allowed = await _retry_vpn_start()
    if allowed:
        _down_checks = 0
        _vpn_retry_delay = 0.0
        # Keep WebUI proxies alive while the tunnel is up (Docker may race start).
        try:
            await asyncio.to_thread(vpn_manager.refresh_local_forwards)
        except Exception as exc:
            logger.debug("VPN WebUI forward refresh failed: %s", exc)
        if _stopped_for_tunnel:
            names = sorted(_stopped_for_tunnel)
            _stopped_for_tunnel.clear()
            restarted = await start_tunneled_apps(names)
            if restarted:
                logger.info("VPN tunnel is up; started %s.", ", ".join(restarted))
                if _wire_after_tunnel:
                    _wire_after_tunnel = False
                    asyncio.create_task(schedule_full_wiring(wait_for_apps=True))
        # Kill any leftover clearnet copies that bypass WireGuard UID routing.
        try:
            leaked = await asyncio.to_thread(vpn_manager.reclaim_clearnet_tunneled_processes)
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
    _down_checks += 1
    if _down_checks <= grace:
        logger.warning("VPN tunnel check failed (%s of %s); not stopping tunneled apps yet.", _down_checks, grace + 1)
        return []
    stopped = await stop_tunneled_apps()
    if stopped:
        _stopped_for_tunnel.update(stopped)
        logger.error(
            "Stopped %s because VPN is enabled but the tunnel is down; they start again when it is back.",
            ", ".join(stopped),
        )
    return stopped


async def vpn_isolation_loop(interval: float = 5.0, grace: int = 2) -> None:
    """Keep tunneled apps off the house WAN if the tunnel drops after they started."""
    while True:
        try:
            await enforce_vpn_isolation(grace=grace)
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
    order = boot_autostart_order(sorted(name for name in wanted if name in VPN_TUNNELED_APPS))
    started: list[str] = []
    pending_listen: list[BaseApplication] = []
    for name in order:
        if name == "prowlarr" and pending_listen:
            await _wait_listeners(pending_listen)
            pending_listen = []
        if not catalog.has(name):
            continue
        plugin = catalog.get(name)
        if not plugin.manifest.daemon or not plugin.is_installed():
            continue
        try:
            await asyncio.to_thread(vpn_manager.assert_can_start_tunneled_app, name)
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
            if name in _LISTEN_BEFORE_ARR:
                pending_listen.append(plugin)
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


async def _wait_listeners(plugins: list[BaseApplication], timeout: float = _LISTEN_WAIT_SECONDS) -> None:
    """Wait until download clients answer, without stacking one timeout per app."""
    if not plugins:
        return
    results = await asyncio.gather(
        *(_wait_healthy(plugin, timeout=timeout) for plugin in plugins),
        return_exceptions=True,
    )
    for plugin, result in zip(plugins, results):
        if result is True:
            continue
        logger.warning(
            "%s did not answer on %s within %.0fs; *Arr may report connection refused until its next check.",
            plugin.manifest.display_name,
            plugin.health_check_url(),
            timeout,
        )


async def start_cloudflare_tunnel_last(
    plugins: list[BaseApplication], timeout: float = _TUNNEL_WAIT_SECONDS
) -> None:
    """Start cloudflared after the dashboard and autostarted apps answer, so it never hits a closed origin."""
    from core.cloudflare_tunnel import cloudflare_tunnel
    from core.jellyfin_cf_origin import jellyfin_cf_origin

    if plugins:
        await asyncio.gather(
            *(_wait_healthy(plugin, timeout=timeout) for plugin in plugins),
            return_exceptions=True,
        )

    jellyfin = next((plugin for plugin in plugins if getattr(plugin, "name", None) == "jellyfin"), None)
    if jellyfin is not None:
        ensure_proxies = getattr(jellyfin, "_ensure_known_proxies", None)
        if callable(ensure_proxies):
            try:
                ensure_proxies()
            except Exception as err:
                logger.debug("Jellyfin KnownProxies ensure skipped: %s", err)
        try:
            origin = await jellyfin_cf_origin.start(upstream_port=int(jellyfin.port))
            if origin.get("status") == "error":
                logger.warning("Jellyfin Cloudflare origin did not start: %s", origin.get("detail"))
        except Exception as err:
            logger.warning("Jellyfin Cloudflare origin did not start: %s", err)
        try:
            await _ensure_jellyfin_tunnel_points_at_cf_origin(int(jellyfin.port))
        except Exception as err:
            logger.debug("Jellyfin tunnel origin sync skipped: %s", err)

    try:
        result = await cloudflare_tunnel.start()
    except Exception as err:
        logger.warning("Cloudflare Tunnel did not start: %s", err)
        return
    if result.get("status") == "error":
        logger.warning("Cloudflare Tunnel did not start: %s", result.get("detail"))


async def _ensure_jellyfin_tunnel_points_at_cf_origin(jellyfin_port: int) -> None:
    """Repoint a previously published Jellyfin hostname onto the CF origin shim."""
    from core.cloudflare_api import api_token_configured, load_hostnames, sync_published_app_port
    from core.jellyfin_cf_origin import jellyfin_tunnel_service_url

    if not api_token_configured():
        return
    if not str((load_hostnames().get("jellyfin") or {}).get("last_published") or "").strip():
        return
    result = await sync_published_app_port("jellyfin", int(jellyfin_port), force=True)
    if result.get("ok") and not result.get("skipped"):
        logger.info(
            "Jellyfin tunnel origin set to %s (X-Forwarded-For shim)",
            jellyfin_tunnel_service_url(),
        )


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
                set_wiring_progress(f"Waiting for {plugin.manifest.display_name} to respond")
                ready = False
                break
            if name in APPS_WITH_FILE_API_KEYS and not await asyncio.to_thread(get_application_api_key, name):
                set_wiring_progress(f"Waiting for {plugin.manifest.display_name} connection details")
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
        hold_for_tunnel(stopped or VPN_TUNNELED_APPS)
        result["started_apps"] = []
    return result
