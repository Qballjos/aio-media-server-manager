"""
core/integrations/credentials.py — Discover and store API credentials for managed applications.

Checks SecretStore first, then falls back to parsing application config files
(e.g., config.xml for *Arr apps, sabnzbd.ini for SABnzbd), and persists discovered
keys into SecretStore.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from pathlib import Path
from typing import Optional

from core.crypto import secret_store
from core.settings import settings

logger = logging.getLogger(__name__)


def get_application_api_key(app_name: str, app_config_dir: Optional[Path] = None) -> Optional[str]:
    """
    Retrieve API key for a given application from the live config file, then SecretStore.
    """
    secret_key_name = f"{app_name.lower()}_api_key"
    cfg_dir = app_config_dir or (settings.config_dir / app_name.lower())
    if not cfg_dir.exists() and app_name.lower() != "sabnzbd":
        stored = secret_store.get_secret(secret_key_name)
        return stored

    api_key: Optional[str] = None

    # Servarr apps (*arr): config.xml contains <ApiKey>...</ApiKey>
    arr_config = cfg_dir / "config.xml"
    if arr_config.exists():
        try:
            content = arr_config.read_text(encoding="utf-8")
            match = re.search(r"<ApiKey>([a-fA-F0-9]{32,})</ApiKey>", content)
            if match:
                api_key = match.group(1)
        except Exception as e:
            logger.debug("Could not read %s: %s", arr_config, e)

    # SABnzbd: prefer the live ini over a stale secret-store copy (SAB regenerates keys).
    if app_name.lower() == "sabnzbd":
        from core.integrations.sabnzbd import read_sabnzbd_ini

        parsed = read_sabnzbd_ini(cfg_dir if cfg_dir.exists() else settings.config_dir / "sabnzbd")
        if parsed.get("api_key"):
            api_key = parsed["api_key"]

    # Fallback: secret store (after disk so regenerated SAB keys win).
    if not api_key:
        stored = secret_store.get_secret(secret_key_name)
        if stored:
            return stored

    if api_key:
        secret_store.save_secret(secret_key_name, api_key)
        return api_key

    return None


# Apps that write an API key to disk after first boot. Flaresolverr / qBittorrent / Plex do not.
APPS_WITH_FILE_API_KEYS = frozenset(
    {"sonarr", "radarr", "lidarr", "prowlarr", "sabnzbd", "bazarr"}
)


async def wait_for_application_api_key(app_name: str, timeout: float = 90.0) -> Optional[str]:
    """Poll config.xml / secret store until the app has generated an API key."""
    if app_name not in APPS_WITH_FILE_API_KEYS:
        return get_application_api_key(app_name)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        key = get_application_api_key(app_name)
        if key:
            return key
        await asyncio.sleep(1.5)
    return get_application_api_key(app_name)


def set_application_api_key(app_name: str, api_key: str) -> None:
    """Store an application's API key into the encrypted SecretStore."""
    secret_key_name = f"{app_name.lower()}_api_key"
    secret_store.save_secret(secret_key_name, api_key)
