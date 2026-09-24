"""Runtime appliance settings that can be changed after first-run."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from core.auth import auth_manager
from core.cloudflare_tunnel import cloudflare_tunnel
from core.crypto import secret_store
from core.integrations.credentials import set_application_api_key
from core.settings import settings
from core.supervisor import ProcessSupervisor, ProcessState
from core.vpn import vpn_manager, PROVIDERS, save_vpn_config_text

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/settings", tags=["Settings"])

GITHUB_TOKEN_SECRET = "github_token"


def _public_updates() -> dict[str, Any]:
    from core.update_schedule import scheduler

    status = scheduler.public_status()
    status["message"] = "Check GitHub on a schedule. Apply can notify only, match the check, or run on its own cadence."
    return status


def _public_backups() -> dict[str, Any]:
    from core.backup_jobs import backup_jobs

    return backup_jobs.public_status()


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
        from core.storage import StorageManager

        info = StorageManager(settings).validate_all()
        for label, item in info.items():
            storage[label] = {
                "path": str(item.path),
                "exists": item.exists,
                "writable": item.writable,
                "fs_type": item.fs_type,
                "hardlinks_supported": item.hardlinks_supported,
                "is_network_fs": item.is_network_fs,
            }
    except Exception as exc:
        logger.debug("storage summary failed: %s", exc)
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
        "root_path": settings.root_path,
        "github_token_configured": bool(token),
        "jellyfin_api_key_configured": bool(secret_store.get_secret("jellyfin_api_key")),
        "seerr_api_key_configured": bool(secret_store.get_secret("seerr_api_key")),
        "vpn": vpn_manager.status(),
        "cloudflare_tunnel": cloudflare_tunnel.status(),
        "storage": storage,
        "bind_mounts_editable": False,
        "updates": _public_updates(),
        "backups": _public_backups(),
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
    if body.vpn_enforce is not None:
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

    if body.vpn_enabled is True:
        vpn_manager.start()
        notes.append("VPN start attempted.")
    elif body.vpn_enabled is False:
        vpn_manager.stop()
        notes.append("VPN stopped.")

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
                logger.warning("Could not restart %s after settings change: %s", name, exc)
        notes.append("Restarted child processes after PUID/PGID change." if restarted else "No running children to restart.")

    payload = public_settings()
    payload["notes"] = notes
    payload["restarted"] = restarted
    return payload
