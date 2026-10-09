"""
api/routers/applications.py — Application Lifecycle & Subprocess Management

Provides controls to start, stop, restart, poll status, and view logs of
managed applications.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse

from pydantic import BaseModel

from applications.catalog import ApplicationCatalog, refresh_live_catalogs
from core.app_prefs import AppPrefsError, autostart_for, set_app_option, update_app_prefs
from core.app_web_url import app_web_ui_url_for_request
from core.auth import auth_manager
from core.integrations.sessions import app_session_cookies
from core.settings import settings
from core.supervisor import ProcessSupervisor
from core.uninstall import UninstallError, uninstall_application
from core.updater import ApplicationUpdater
from core.vpn import VPN_TUNNELED_APPS, VpnIsolationError, vpn_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/applications", tags=["Applications"])

catalog = ApplicationCatalog(app_settings=settings)
API_KEY_APPS = frozenset({"jellyfin", "seerr"})
updater = ApplicationUpdater(app_settings=settings)


class AppSettingsPatch(BaseModel):
    port: int | None = None
    autostart: bool | None = None
    vuetorrent: bool | None = None
    vuetorrent_update: bool | None = None
    api_key: str | None = None
    restart: bool = True


class UninstallRequest(BaseModel):
    remove_application: bool = True
    remove_config: bool = False
    remove_data: bool = False


def _ensure_authenticated(request: Request) -> None:
    if not auth_manager.setup_required():
        auth_manager.authenticate_request(request)


@router.get("", summary="List managed applications and live statuses")
async def list_applications(request: Request) -> dict[str, Any]:
    """
    Returns live process and health state for all catalog applications.
    """
    _ensure_authenticated(request)
    supervisor = ProcessSupervisor.get()
    active_procs = {p["name"]: p for p in supervisor.list_processes()}

    results = []
    for plugin in catalog.all_plugins():
        name = plugin.name
        proc_info = active_procs.get(name)

        is_installed = plugin.is_installed()
        meta = plugin.installed_metadata() if is_installed else {}

        state = proc_info["state"] if proc_info else "stopped"
        pid = proc_info["pid"] if proc_info else None
        started_at = proc_info["started_at"] if proc_info else None
        uptime = int(time.monotonic() - started_at) if (started_at and state == "running") else 0
        is_crash_loop = proc_info.get("is_crash_loop", False) if proc_info else False
        recent_crashes = proc_info.get("recent_crashes", 0) if proc_info else 0
        autostart = autostart_for(name, default=plugin.manifest.daemon)

        results.append(
            {
                "name": name,
                "display_name": plugin.manifest.display_name,
                "category": plugin.manifest.category.value,
                "tier": plugin.manifest.tier.value,
                "port": plugin.port,
                "default_port": plugin.manifest.default_port,
                "autostart": autostart,
                "installed": is_installed,
                "installed_version": meta.get("version"),
                "state": state,
                "pid": pid,
                "uptime_seconds": uptime,
                "is_crash_loop": is_crash_loop,
                "recent_crashes": recent_crashes,
                "health_url": plugin.health_check_url(),
                "web_ui_url": app_web_ui_url_for_request(
                    request, app_name=plugin.name, port=plugin.port
                ),
                "daemon": plugin.manifest.daemon,
            }
        )

    return {"applications": results}


@router.post("/{name}/session", summary="Sign the manager admin in to an app for this browser")
async def app_session(name: str, request: Request) -> JSONResponse:
    """Log the shared admin in to the app server-side and hand the browser the session.

    The dashboard calls this before opening an app. Browsers do not isolate cookies
    by port, so a host-only cookie set here is also sent to http://<same host>:<app
    port>. On public subdomains the hosts differ, so the app keeps its own login.
    """
    _ensure_authenticated(request)
    try:
        plugin = catalog.get(name)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    target = app_web_ui_url_for_request(request, app_name=plugin.name, port=plugin.port)
    same_host = (urlparse(target).hostname or "") == (request.url.hostname or "")
    jar = None
    if same_host:
        plex_dir = catalog.get("plex").config_dir if catalog.has("plex") else None
        jar = await asyncio.to_thread(
            app_session_cookies, plugin.name, plugin.port, plex_config_dir=plex_dir
        )
    response = JSONResponse({"url": target, "signed_in": bool(jar)})
    for cookie in jar or []:
        max_age = None
        if cookie.expires:
            max_age = max(0, int(cookie.expires - time.time()))
        response.set_cookie(
            cookie.name,
            cookie.value,
            max_age=max_age,
            path="/",
            secure=request.url.scheme == "https",
            httponly=True,
            samesite="lax",
        )
    return response


@router.post("/{name}/start", summary="Start an application process")
async def start_application(name: str, request: Request) -> dict[str, Any]:
    """
    Launches the application's executable via ProcessSupervisor.
    """
    _ensure_authenticated(request)
    try:
        plugin = catalog.get(name)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    if not plugin.is_installed():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot start '{name}' because it is not installed.",
        )
    if not plugin.manifest.daemon:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"'{name}' is a CLI tool and is not started as a background service.",
        )

    if name in VPN_TUNNELED_APPS:
        try:
            vpn_manager.assert_can_start_tunneled_app(name)
        except VpnIsolationError as err:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(err)) from err

    supervisor = ProcessSupervisor.get()
    cmd = plugin.start_command()
    env = plugin.extra_env()
    cwd = plugin.working_directory()
    log_dir = settings.config_dir / "logs"

    try:
        await supervisor.start(
            name=name,
            cmd=cmd,
            cwd=cwd,
            env=env,
            log_dir=log_dir,
        )
    except RuntimeError as err:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(err))

    return {
        "status": "started",
        "name": name,
        "state": supervisor.status(name).value,
    }


@router.post("/{name}/stop", summary="Stop an application process")
async def stop_application(name: str, request: Request) -> dict[str, Any]:
    """
    Gracefully stops the application process.
    """
    _ensure_authenticated(request)
    try:
        catalog.get(name)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    supervisor = ProcessSupervisor.get()
    try:
        await supervisor.stop(name)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Error stopping '%s': %s", name, exc)

    return {
        "status": "stopped",
        "name": name,
        "state": supervisor.status(name).value,
    }


@router.post("/{name}/restart", summary="Restart an application process")
async def restart_application(name: str, request: Request) -> dict[str, Any]:
    """
    Stops then restarts the application process.
    """
    _ensure_authenticated(request)
    try:
        plugin = catalog.get(name)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    supervisor = ProcessSupervisor.get()
    if name in VPN_TUNNELED_APPS and not vpn_manager.tunneled_apps_allowed():
        if supervisor.status(name).value == "running":
            try:
                await supervisor.stop(name)
            except Exception as exc:
                logger.warning("Error stopping '%s' for VPN isolation: %s", name, exc)
        try:
            vpn_manager.assert_can_start_tunneled_app(name)
        except VpnIsolationError as err:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(err)) from err

    try:
        if supervisor.status(name).value == "stopped":
            # If stopped, simply start it
            cmd = plugin.start_command()
            await supervisor.start(
                name=name,
                cmd=cmd,
                cwd=plugin.working_directory(),
                env=plugin.extra_env(),
                log_dir=settings.config_dir / "logs",
            )
        else:
            await supervisor.restart(name)
    except VpnIsolationError as err:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(err)) from err

    return {
        "status": "restarted",
        "name": name,
        "state": supervisor.status(name).value,
    }


from core.log_redactor import redact_log_line


@router.get("/{name}/logs", summary="Get application process logs")
async def get_application_logs(name: str, request: Request) -> dict[str, Any]:
    """
    Returns recent stdout/stderr output lines for an application with secrets redacted.
    """
    _ensure_authenticated(request)
    try:
        catalog.get(name)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    supervisor = ProcessSupervisor.get()
    raw_logs = supervisor.get_logs(name)
    scrubbed_logs = [redact_log_line(line) for line in raw_logs]

    return {
        "name": name,
        "lines": scrubbed_logs,
    }


def _application_settings(plugin, request: Request) -> dict[str, Any]:
    supervisor = ProcessSupervisor.get()
    state = supervisor.status(plugin.name).value
    notes = []
    if plugin.name == "plex":
        notes.append(
            "Plex Media Server usually stays on 32400. This field updates the Open UI link; "
            "change the listen port inside Plex as well if you retarget it."
        )
    elif plugin.name in VPN_TUNNELED_APPS:
        notes.append(
            "This app can run inside the torrent VPN namespace. After a port change, restart "
            "the VPN tunnel so local forwarding matches."
        )
    if plugin.name == "recyclarr":
        notes.append(
            "Recyclarr is a one-shot CLI. Use Settings to pick TRaSH profiles, edit recyclarr.yml, "
            "or restore defaults. Sync on the card, Auto-Wire, or Sync now runs recyclarr sync against Sonarr/Radarr."
        )
    elif plugin.name == "qbittorrent":
        notes.append(
            "VueTorrent is the default WebUI (downloaded from GitHub on install/start). "
            "Turn it off for the stock UI, or use Update VueTorrent to replace files with the latest release. "
            "The WebAPI stays the same for Sonarr, Radarr, and Lidarr."
        )
    elif plugin.name == "jellyfin":
        notes.append(
            "Paste an API key from Jellyfin Dashboard → API Keys if homepage Recently added cannot log in automatically."
        )
    elif plugin.name == "seerr":
        notes.append(
            "Paste the API key from Seerr Settings → General if homepage search and requests cannot find it automatically."
        )
    elif plugin.manifest.daemon:
        notes.append(
            "Open UI uses http://<host>:<port> on LAN, or https://<subdomain>.<domain> over Cloudflare. "
            "If this app is published and you change the listen port, AIO updates the published "
            "application service URL when a Cloudflare API token is saved (DNS still points at the tunnel)."
        )
    else:
        notes.append("This is a CLI/sync tool, not a background WebUI service.")
    payload = {
        "name": plugin.name,
        "display_name": plugin.manifest.display_name,
        "port": plugin.port,
        "default_port": plugin.manifest.default_port,
        "autostart": autostart_for(plugin.name, default=plugin.manifest.daemon),
        "daemon": plugin.manifest.daemon,
        "installed": plugin.is_installed(),
        "state": state,
        "config_dir": str(plugin.config_dir),
        "install_dir": str(plugin.install_dir),
        "data_dir": str(plugin.data_dir),
        "health_url": plugin.health_check_url(),
        "help_url": plugin.manifest.to_dict().get("help_url") or plugin.manifest.upstream_url,
        "vpn_tunneled": plugin.name in VPN_TUNNELED_APPS,
        "notes": notes,
    }
    if plugin.name == "qbittorrent":
        from applications.qbittorrent.vuetorrent import (
            VUETORRENT_HELP,
            installed_meta,
            ui_ready,
            vuetorrent_dir,
            vuetorrent_enabled,
        )

        payload["vuetorrent"] = vuetorrent_enabled()
        payload["vuetorrent_installed"] = ui_ready(plugin.config_dir)
        payload["vuetorrent_version"] = installed_meta(plugin.config_dir).get("version")
        payload["vuetorrent_path"] = str(vuetorrent_dir(plugin.config_dir))
        payload["vuetorrent_help"] = VUETORRENT_HELP
    if plugin.name in API_KEY_APPS:
        from core.crypto import secret_store

        payload["api_key_configured"] = bool(secret_store.get_secret(f"{plugin.name}_api_key"))
    if plugin.name == "neutarr":
        from core.integrations.local_auth import read_neutarr_setup_token

        payload["setup_token"] = read_neutarr_setup_token(plugin.config_dir) or ""
    return payload


@router.get("/{name}/settings", summary="Read per-application settings")
async def get_application_settings(name: str, request: Request) -> dict[str, Any]:
    _ensure_authenticated(request)
    try:
        plugin = catalog.get(name)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return _application_settings(plugin, request)


@router.patch("/{name}/settings", summary="Update per-application port and autostart")
async def patch_application_settings(
    name: str,
    request: Request,
    body: AppSettingsPatch,
) -> dict[str, Any]:
    _ensure_authenticated(request)
    try:
        plugin = catalog.get(name)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if (
        body.port is None
        and body.autostart is None
        and body.vuetorrent is None
        and body.vuetorrent_update is None
        and body.api_key is None
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No settings to change.")

    taken = {item.name: item.port for item in catalog.all_plugins()}
    try:
        if body.port is not None or body.autostart is not None:
            update_app_prefs(
                name,
                port=body.port,
                autostart=body.autostart,
                reserved_ports={settings.api_port},
                taken_by=taken,
            )
    except AppPrefsError as err:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(err)) from err

    refresh_live_catalogs()
    plugin = catalog.get(name)
    tunnel_sync: dict[str, Any] | None = None
    if body.port is not None:
        plugin.apply_listen_port(body.port)
        try:
            from core.cloudflare_api import (
                CloudflareApiError,
                api_token_configured,
                sync_published_app_port,
            )
            from core.public_hostnames import load_hostnames

            published = load_hostnames().get(name) or {}
            if published.get("last_published"):
                if api_token_configured():
                    tunnel_sync = await sync_published_app_port(name, int(body.port))
                else:
                    tunnel_sync = {
                        "ok": False,
                        "skipped": True,
                        "detail": (
                            "Port saved. Add a Cloudflare API token and publish again "
                            "so the tunnel points at the new port."
                        ),
                    }
        except CloudflareApiError as exc:
            logger.warning("Cloudflare port sync for %s failed: %s", name, exc)
            tunnel_sync = {"ok": False, "detail": str(exc)}
        except Exception as exc:
            logger.warning("Cloudflare port sync for %s failed: %s", name, exc)
            tunnel_sync = {"ok": False, "detail": str(exc)}

    vuetorrent_changed = False
    if body.vuetorrent is not None or body.vuetorrent_update:
        if plugin.name != "qbittorrent":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="VueTorrent is only available for qBittorrent.",
            )
        from applications.qbittorrent.vuetorrent import (
            alternative_ui_root,
            ensure_vuetorrent,
            vuetorrent_enabled,
        )
        from applications.qbittorrent.webui import ensure_webui_localhost_access
        from core.integrations.qbittorrent import target_webui_credentials

        try:
            previously_on = vuetorrent_enabled()
            enable = previously_on if body.vuetorrent is None else bool(body.vuetorrent)
            if body.vuetorrent_update:
                enable = True
            set_app_option("qbittorrent", "vuetorrent", enable)
            if enable:
                # Fresh enable or explicit update → replace files with latest release.
                force = bool(body.vuetorrent_update) or not previously_on
                await asyncio.to_thread(
                    ensure_vuetorrent, plugin.config_dir, force=force
                )
            username, password = target_webui_credentials()
            ensure_webui_localhost_access(
                plugin.config_dir,
                username=username,
                password=password,
                alternative_ui_root=alternative_ui_root(plugin.config_dir),
            )
            vuetorrent_changed = True
        except Exception as exc:
            logger.warning("VueTorrent install/apply failed: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Could not apply VueTorrent: {exc}",
            ) from exc

    if body.api_key is not None:
        if plugin.name not in API_KEY_APPS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="API key can only be saved for Jellyfin or Seerr.",
            )
        from core.crypto import secret_store
        from core.integrations.credentials import set_application_api_key

        key = body.api_key.strip()
        if key:
            set_application_api_key(plugin.name, key)
        else:
            secret_store.delete_secret(f"{plugin.name}_api_key")

    restarted = False
    supervisor = ProcessSupervisor.get()
    running = supervisor.status(name).value == "running"
    should_restart = body.restart and running and plugin.manifest.daemon and (
        body.port is not None or vuetorrent_changed
    )
    if should_restart:
        await supervisor.stop(name)
        try:
            if name in VPN_TUNNELED_APPS:
                vpn_manager.assert_can_start_tunneled_app(name)
            await supervisor.start(
                name=name,
                cmd=plugin.start_command(),
                cwd=plugin.working_directory(),
                env=plugin.extra_env(),
                log_dir=settings.config_dir / "logs",
            )
            restarted = True
        except VpnIsolationError as err:
            logger.warning("Left '%s' stopped after settings change: %s", name, err)

    payload = _application_settings(plugin, request)
    payload["restarted"] = restarted
    payload["status"] = "updated"
    if tunnel_sync is not None:
        payload["cloudflare_tunnel_sync"] = tunnel_sync
    return payload


@router.post("/{name}/reset-crash-loop", summary="Reset crash loop state")
async def reset_application_crash_loop(name: str, request: Request) -> dict[str, Any]:
    """
    Clears recorded crash timestamps and allows the supervisor to restart the application.
    """
    _ensure_authenticated(request)
    try:
        catalog.get(name)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    supervisor = ProcessSupervisor.get()
    supervisor.reset_crash_loop(name)

    return {
        "status": "reset",
        "name": name,
        "state": supervisor.status(name).value,
    }


@router.get("/{name}/updates", summary="Check whether an application update is available")
async def check_application_update(name: str, request: Request) -> dict[str, Any]:
    _ensure_authenticated(request)
    try:
        plugin = catalog.get(name)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return updater.update_available(plugin)


@router.post("/{name}/update", summary="Update an application with rollback on failure")
async def update_application(name: str, request: Request) -> dict[str, Any]:
    _ensure_authenticated(request)
    try:
        plugin = catalog.get(name)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if not plugin.is_installed():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot update '{name}' because it is not installed.",
        )
    from core.maintenance import update_in_progress

    with update_in_progress():
        return await updater.update(plugin)


@router.post("/{name}/uninstall", summary="Uninstall an application")
async def uninstall_managed_application(
    name: str,
    request: Request,
    body: UninstallRequest | None = None,
) -> dict[str, Any]:
    _ensure_authenticated(request)
    try:
        plugin = catalog.get(name)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    payload = body or UninstallRequest()
    try:
        return await uninstall_application(
            plugin,
            remove_application=payload.remove_application,
            remove_config=payload.remove_config,
            remove_data=payload.remove_data,
        )
    except UninstallError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Uninstall of %s failed: %s", name, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Uninstall of '{name}' failed: {exc}",
        ) from exc

