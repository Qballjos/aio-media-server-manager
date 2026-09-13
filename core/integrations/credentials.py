"""
core/integrations/credentials.py — Discover and store API credentials for managed applications.

Checks SecretStore first, then falls back to parsing application config files
(e.g., config.xml for *Arr apps, sabnzbd.ini for SABnzbd), and persists discovered
keys into SecretStore.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

from core.crypto import secret_store
from core.settings import settings

logger = logging.getLogger(__name__)


def get_application_api_key(app_name: str, app_config_dir: Optional[Path] = None) -> Optional[str]:
    """
    Retrieve API key for a given application from SecretStore or configuration file.
    """
    secret_key_name = f"{app_name.lower()}_api_key"
    stored = secret_store.get_secret(secret_key_name)
    if stored:
        return stored

    cfg_dir = app_config_dir or (settings.config_dir / app_name.lower())
    if not cfg_dir.exists():
        return None

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

    # SABnzbd: sabnzbd.ini contains api_key = ...
    sab_config = cfg_dir / "sabnzbd.ini"
    if sab_config.exists() and not api_key:
        try:
            content = sab_config.read_text(encoding="utf-8")
            match = re.search(r"(?i)^api_key\s*=\s*([a-fA-F0-9]{32,})", content, re.MULTILINE)
            if match:
                api_key = match.group(1)
        except Exception as e:
            logger.debug("Could not read %s: %s", sab_config, e)

    if api_key:
        secret_store.save_secret(secret_key_name, api_key)
        return api_key

    return None


def set_application_api_key(app_name: str, api_key: str) -> None:
    """Store an application's API key into the encrypted SecretStore."""
    secret_key_name = f"{app_name.lower()}_api_key"
    secret_store.save_secret(secret_key_name, api_key)
