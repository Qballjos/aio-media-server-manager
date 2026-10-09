"""Runtime appliance settings that can be changed after first-run."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from core.auth import auth_manager
from core import branding as branding_mod
from core.cloudflare_tunnel import cloudflare_tunnel
from core.crypto import secret_store
from core.integrations.credentials import set_application_api_key
from core.settings import settings
from core.supervisor import ProcessSupervisor, ProcessState
from core.vpn import VPN_TUNNELED_APPS, VpnIsolationError, vpn_manager, PROVIDERS, save_vpn_config_text

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/settings", tags=["Settings"])

GITHUB_TOKEN_SECRET = "github_token"


def _public_updates() -> dict[str, Any]:
    from core.update_schedule import scheduler

    status = scheduler.public_status()
    status["message"] = (
        "Check GitHub on a schedule. Catalog apply can notify only, match the check, "
        "or run on its own cadence. Appliance image updates are notified only."
    )
    return status


def _public_backups() -> dict[str, Any]:
    from core.backup_jobs import backup_jobs

    return backup_jobs.public_status()


def _homepage_key_status(name: str) -> dict[str, Any]:
    """Saved vs working status for Settings → Homepage keys. Never returns the secret."""
    from applications.catalog import ApplicationCatalog
    from core.supervisor import ProcessState, ProcessSupervisor

    key = (secret_store.get_secret(f"{name}_api_key") or "").strip()
    catalog = ApplicationCatalog()
    installed = False
    running = False
    port = 0
    config_dir = None
    if catalog.has(name):
        plugin = catalog.get(name)
        installed = bool(plugin.is_installed())
        port = int(plugin.port or 0)
        config_dir = plugin.config_dir
        state = ProcessSupervisor.get().status(name)
        running = getattr(state, "value", state) == ProcessState.RUNNING.value
    if not key and name == "seerr":
        from core.integrations.seerr import read_seerr_api_key

        key = (read_seerr_api_key(config_dir) or "").strip()
    configured = bool(key)
    working = False
    detail = "No API key saved."
    if configured and not installed:
        detail = "Saved. App is not installed."
    elif configured and not running:
        detail = "Saved. App is stopped."
    elif configured and running:
        working, probe = _probe_homepage_key(name, key, port)
        detail = "Working." if working else (probe or "Saved, but the app did not accept the key.")
    elif running:
        detail = "App is running, but no API key is saved."
    return {
        "configured": configured,
        "installed": installed,
        "running": running,
        "working": working,
        "detail": detail,
    }


def _probe_homepage_key(name: str, key: str, port: int) -> tuple[bool, str]:
    if not port:
        return False, "Saved, but the app port is unknown."
    try:
        import requests
    except Exception:
        return False, "Saved."
    try:
        if name == "jellyfin":
            from core.integrations.jellyfin import jellyfin_auth_headers

            resp = requests.get(
                f"http://127.0.0.1:{port}/System/Info",
                headers=jellyfin_auth_headers(key),
                timeout=2.0,
            )
        elif name == "seerr":
            resp = requests.get(
                f"http://127.0.0.1:{port}/api/v1/settings/main",
                headers={"X-Api-Key": key, "Content-Type": "application/json"},
                timeout=2.0,
            )
        else:
            return False, "Saved."
        if resp.status_code < 400:
            return True, "Working."
        return False, f"Saved, but the app rejected the key (HTTP {resp.status_code})."
    except Exception:
        return False, "Saved, but the app did not answer."


def _ensure_authenticated(request: Request) -> str:
    if auth_manager.setup_required():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Setup required.")
    return auth_manager.authenticate_request(request)


class SettingsPatch(BaseModel):
    timezone: Optional[str] = None
    log_level: Optional[str] = None
    puid: Optional[int] = Field(default=None, gt=0)
    pgid: Optional[int] = Field(default=None, gt=0)
    backup_retention: Optional[int] = Field(default=None, ge=1, le=90)
    vpn_enabled: Optional[bool] = None
    vpn_enforce: Optional[bool] = None
    vpn_provider: Optional[str] = None
    vpn_protocol: Optional[str] = None
    vpn_config_path: Optional[str] = None
    vpn_config_text: Optional[str] = None
    cloudflare_tunnel_enabled: Optional[bool] = None
    cloudflare_tunnel_token: Optional[str] = None
    trusted_proxies: Optional[str] = None
    public_app_base_domain: Optional[str] = None
    github_token: Optional[str] = None
    jellyfin_api_key: Optional[str] = None
    seerr_api_key: Optional[str] = None
    restart_children: bool = False
    update_check_schedule: Optional[str] = None
    update_apply_schedule: Optional[str] = None
    update_time: Optional[str] = None
    update_weekday: Optional[int] = Field(default=None, ge=0, le=6)
    update_day_of_month: Optional[int] = Field(default=None, ge=1, le=28)
    backup_schedule: Optional[str] = None
    backup_time: Optional[str] = None
    backup_weekday: Optional[int] = Field(default=None, ge=0, le=6)
    backup_day_of_month: Optional[int] = Field(default=None, ge=1, le=28)


def _apply_timezone(value: str) -> None:
    settings.timezone = (value or "UTC").strip() or "UTC"
    settings.apply_timezone()


def _apply_log_level(value: str) -> None:
    level = str(value).upper()
    valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    if level not in valid:
        raise ValueError(f"log_level must be one of {sorted(valid)}.")
    settings.log_level = level
    logging.getLogger().setLevel(getattr(logging, level, logging.INFO))


def public_settings() -> dict[str, Any]:
    token = settings.github_token or secret_store.get_secret(GITHUB_TOKEN_SECRET)
    if token and not settings.github_token:
        settings.github_token = token
    storage = {}
    try:
        import psutil

        from core.storage import StorageManager

        info = StorageManager(settings).validate_all()
        for label, item in info.items():
            entry = {
                "path": str(item.path),
                "exists": item.exists,
                "writable": item.writable,
                "fs_type": item.fs_type,
                "hardlinks_supported": item.hardlinks_supported,
                "is_network_fs": item.is_network_fs,
            }
            try:
                usage = psutil.disk_usage(str(item.path) if item.exists else "/")
                entry["disk_total"] = usage.total
                entry["disk_used"] = usage.used
                entry["disk_percent"] = usage.percent
            except Exception:
                entry["disk_total"] = 0
                entry["disk_used"] = 0
                entry["disk_percent"] = 0
            storage[label] = entry
    except Exception as exc:
        logger.debug("storage summary failed: %s", exc)
    jellyfin_key = _homepage_key_status("jellyfin")
    seerr_key = _homepage_key_status("seerr")
    return {
        "timezone": settings.timezone,
        "log_level": settings.log_level,
        "puid": settings.puid,
        "pgid": settings.pgid,
        "backup_retention": settings.backup_retention,
        "backup_dir": str(settings.backup_dir),
        "config_dir": str(settings.config_dir),
        "download_dir": str(settings.download_dir),
        "media_dir": str(settings.media_dir),
        "api_host": settings.api_host,
        "api_port": settings.api_port,
        "trusted_proxies": settings.trusted_proxies,
        "public_app_base_domain": settings.public_app_base_domain,
        "root_path": settings.root_path,
        "github_token_configured": bool(token),
        "homepage_keys": {"jellyfin": jellyfin_key, "seerr": seerr_key},
        "jellyfin_api_key_configured": jellyfin_key["configured"],
        "seerr_api_key_configured": seerr_key["configured"],
        "vpn": vpn_manager.status(),
        "cloudflare_tunnel": cloudflare_tunnel.status(),
        "storage": storage,
        "bind_mounts_editable": False,
        "updates": _public_updates(),
        "backups": _public_backups(),
        "branding": branding_mod.public_branding(),
    }


@router.get("", summary="Load editable appliance settings")
async def get_settings(request: Request) -> dict[str, Any]:
    _ensure_authenticated(request)
    return public_settings()


@router.patch("", summary="Update appliance settings")
async def patch_settings(body: SettingsPatch, request: Request) -> dict[str, Any]:
    _ensure_authenticated(request)
    notes: list[str] = []
    restart_needed = False
    # Capture before mutation so re-saving vpn_enabled=true does not bounce tunneled apps.
    vpn_was_enabled = bool(settings.vpn_enabled)

    if body.timezone is not None:
        _apply_timezone(body.timezone)
    if body.log_level is not None:
        try:
            _apply_log_level(body.log_level)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    if body.puid is not None and body.puid != settings.puid:
        settings.puid = body.puid
        restart_needed = True
    if body.pgid is not None and body.pgid != settings.pgid:
        settings.pgid = body.pgid
        restart_needed = True
    if body.backup_retention is not None:
        settings.backup_retention = body.backup_retention
    if body.vpn_enabled is not None:
        settings.vpn_enabled = body.vpn_enabled
        # Kill switch tracks the VPN switch: on = fail-closed, off = house network.
        settings.vpn_enforce = bool(body.vpn_enabled)
    if body.vpn_enforce is not None and not settings.vpn_enabled:
        settings.vpn_enforce = body.vpn_enforce
    if body.vpn_provider is not None:
        provider = body.vpn_provider.strip().lower()
        if provider not in PROVIDERS:
            raise HTTPException(status_code=422, detail="Unsupported VPN provider.")
        settings.vpn_provider = provider
    if body.vpn_protocol is not None:
        proto = body.vpn_protocol.strip().lower()
        if proto not in {"wireguard", "openvpn"}:
            raise HTTPException(status_code=422, detail="vpn_protocol must be wireguard or openvpn.")
        settings.vpn_protocol = proto
    if body.vpn_config_path is not None:
        requested = body.vpn_config_path.strip()
        if requested:
            settings.vpn_config_path = Path(requested).expanduser()
    if body.vpn_config_text:
        try:
            dest = save_vpn_config_text(
                settings,
                body.vpn_config_text,
                protocol=settings.vpn_protocol,
                path=str(settings.vpn_config_path) if settings.vpn_config_path else None,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        notes.append(f"Wrote VPN config to {dest}.")
    if body.trusted_proxies is not None:
        settings.trusted_proxies = body.trusted_proxies.strip()
        notes.append(
            "Trusted proxies saved. Recreate/restart the AIO container for proxy trust to apply "
            "(it is read at process start)."
        )
    if body.public_app_base_domain is not None:
        domain = body.public_app_base_domain.strip().strip(".").lower()
        if domain.startswith("http://") or domain.startswith("https://"):
            raise HTTPException(
                status_code=422,
                detail="public_app_base_domain is a DNS zone only (e.g. example.com), not a URL.",
            )
        settings.public_app_base_domain = domain
        from core.homepage import clear_homepage_snapshot_cache

        clear_homepage_snapshot_cache()
        try:
            from applications.shelfmark_mirrors import sync_shelfmark_audiobook_library_url

            sync_shelfmark_audiobook_library_url(settings.config_dir / "shelfmark")
        except Exception:
            pass
        notes.append(
            "Public app domain saved. Home and Catalog Open UI links use https://<app>."
            + (domain or "<derived-host>")
            + " when you are not on the LAN."
        )
    if body.cloudflare_tunnel_enabled is not None:
        settings.cloudflare_tunnel_enabled = body.cloudflare_tunnel_enabled
    if body.cloudflare_tunnel_token:
        settings.cloudflare_tunnel_token = body.cloudflare_tunnel_token.strip()
        cloudflare_tunnel.persist_token()
    if body.github_token is not None:
        token = body.github_token.strip()
        if token:
            secret_store.save_secret(GITHUB_TOKEN_SECRET, token)
            settings.github_token = token
        else:
            secret_store.delete_secret(GITHUB_TOKEN_SECRET)
            settings.github_token = None
    for app_name, label, value in (
        ("jellyfin", "Jellyfin", body.jellyfin_api_key),
        ("seerr", "Seerr", body.seerr_api_key),
    ):
        if value is None:
            continue
        key = value.strip()
        if key:
            set_application_api_key(app_name, key)
            notes.append(f"Saved {label} API key.")
        else:
            secret_store.delete_secret(f"{app_name}_api_key")
            notes.append(f"Cleared {label} API key.")
    if body.update_check_schedule is not None or body.update_apply_schedule is not None or body.update_time is not None:
        from core.update_schedule import normalize_apply_schedule, normalize_check_schedule, parse_hhmm

        if body.update_check_schedule is not None:
            settings.update_check_schedule = normalize_check_schedule(body.update_check_schedule)
        if body.update_apply_schedule is not None:
            settings.update_apply_schedule = normalize_apply_schedule(body.update_apply_schedule)
        if body.update_time is not None:
            hour, minute = parse_hhmm(body.update_time)
            settings.update_time = f"{hour:02d}:{minute:02d}"
    if body.update_weekday is not None:
        settings.update_weekday = int(body.update_weekday) % 7
    if body.update_day_of_month is not None:
        settings.update_day_of_month = body.update_day_of_month
    if body.backup_schedule is not None:
        from core.update_schedule import normalize_check_schedule

        settings.backup_schedule = normalize_check_schedule(body.backup_schedule)
    if body.backup_time is not None:
        from core.update_schedule import parse_hhmm

        hour, minute = parse_hhmm(body.backup_time)
        settings.backup_time = f"{hour:02d}:{minute:02d}"
    if body.backup_weekday is not None:
        settings.backup_weekday = int(body.backup_weekday) % 7
    if body.backup_day_of_month is not None:
        settings.backup_day_of_month = body.backup_day_of_month

    try:
        settings.save()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not save settings: {exc}") from exc

    if body.vpn_enabled is True and not vpn_was_enabled:
        from core.integrations.lifecycle import bring_up_vpn

        result = await bring_up_vpn(vpn_manager)
        if result.get("status") == "error":
            notes.append(f"VPN start failed: {result.get('detail') or 'unknown error'}.")
            notes.append("qBittorrent, Prowlarr, and Flaresolverr are stopped so they cannot leak.")
        elif result.get("tunnel_up"):
            started = result.get("started_apps") or []
            notes.append("VPN started.")
            if started:
                notes.append("Started " + ", ".join(started) + " on the tunnel.")
        else:
            notes.append(
                "VPN start ran but the tunnel is still down. "
                "qBittorrent, Prowlarr, and Flaresolverr stay stopped."
            )
    elif body.vpn_enabled is True and vpn_was_enabled:
        notes.append("VPN settings saved. Tunnel left running; use Restart if you changed the profile.")
    elif body.vpn_enabled is False and vpn_was_enabled:
        from core.integrations.lifecycle import start_tunneled_apps, stop_tunneled_apps

        stopped = await stop_tunneled_apps()
        await asyncio.to_thread(vpn_manager.stop)
        # Isolation may already have stopped tunneled apps while the tunnel was down.
        # With VPN off they may run on the house network again.
        started = await start_tunneled_apps(stopped or None)
        notes.append("VPN stopped. Kill switch is off — qBittorrent, Prowlarr, and Flaresolverr can use the house network.")
        if started:
            notes.append("Started " + ", ".join(started) + " on the house network.")
    elif body.vpn_enabled is False and not vpn_was_enabled:
        notes.append("VPN already off.")

    if body.cloudflare_tunnel_enabled is True:
        result = await cloudflare_tunnel.start()
        notes.append(f"Cloudflare Tunnel: {result.get('status')}")
    elif body.cloudflare_tunnel_enabled is False:
        result = await cloudflare_tunnel.stop()
        notes.append(f"Cloudflare Tunnel: {result.get('status')}")

    restarted: list[str] = []
    if restart_needed or body.restart_children:
        from applications.catalog import ApplicationCatalog

        supervisor = ProcessSupervisor.get()
        catalog = ApplicationCatalog()
        for proc in supervisor.list_processes():
            if proc.get("state") != ProcessState.RUNNING.value:
                continue
            name = proc["name"]
            try:
                await supervisor.stop(name)
                if catalog.has(name):
                    plugin = catalog.get(name)
                    if name in VPN_TUNNELED_APPS:
                        vpn_manager.assert_can_start_tunneled_app(name)
                    await supervisor.start(
                        name=name,
                        cmd=plugin.start_command(),
                        cwd=plugin.working_directory(),
                        env=plugin.extra_env(),
                        log_dir=settings.config_dir / "logs",
                    )
                else:
                    await supervisor.restart(name)
                restarted.append(name)
            except Exception as exc:
                if isinstance(exc, VpnIsolationError):
                    logger.warning("Left '%s' stopped after settings change: %s", name, exc)
                else:
                    logger.warning("Could not restart %s after settings change: %s", name, exc)
        notes.append("Restarted child processes after PUID/PGID change." if restarted else "No running children to restart.")

    payload = public_settings()
    payload["notes"] = notes
    payload["restarted"] = restarted
    return payload
