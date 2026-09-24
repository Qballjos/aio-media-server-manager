"""
core/integrations/seerr.py — Seerr (Overseerr/Jellyseerr) REST API Client.

Connects Seerr to media servers (Jellyfin/Plex) and automation apps (Sonarr/Radarr)
so user media requests automatically route to the appropriate downloader and library.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional
import requests

logger = logging.getLogger(__name__)


def read_seerr_api_key(config_dir: Path | None) -> str:
    """Read Seerr/Jellyseerr apiKey from settings.json (written after first setup)."""
    if not config_dir:
        return ""
    root = Path(config_dir)
    candidates = [root / "settings.json", root / "settings" / "main.json"]
    if root.is_dir():
        candidates.extend(sorted(root.glob("**/settings.json"))[:8])
    seen: set[Path] = set()
    for path in candidates:
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        key = _find_api_key(data)
        if key:
            return key
    return ""


def _find_api_key(obj: Any) -> str:
    if isinstance(obj, dict):
        for name in ("apiKey", "api_key"):
            value = str(obj.get(name) or "").strip()
            if len(value) >= 20:
                return value
        nested = obj.get("main")
        if isinstance(nested, dict):
            found = _find_api_key(nested)
            if found:
                return found
        for value in obj.values():
            found = _find_api_key(value)
            if found:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _find_api_key(item)
            if found:
                return found
    return ""


def discover_seerr_api_key(config_dir: Path | None = None, port: int = 5055) -> str:
    """Initialize or sign in, then read apiKey from Seerr settings."""
    from core.app_prefs import load_app_ports
    from core.shared_credentials import admin_email, shared_admin_credentials

    disk = read_seerr_api_key(config_dir)
    if disk:
        return disk
    creds = shared_admin_credentials()
    if not creds:
        return ""
    username, password = creds
    email = (admin_email() or "").strip() or f"{username}@localhost"
    try:
        port = int(load_app_ports().get("seerr") or port or 5055)
    except Exception:
        port = int(port or 5055)
    client = SeerrClient(port=port)
    client.setup_local_admin(email, username, password)
    session = requests.Session()
    try:
        login = session.post(
            f"{client.base_url}/auth/local",
            json={"email": email, "username": username, "password": password},
            timeout=8.0,
        )
        if login.status_code not in (200, 201):
            login = session.post(
                f"{client.base_url}/auth/local",
                json={"email": email, "password": password},
                timeout=8.0,
            )
        if login.status_code not in (200, 201):
            return read_seerr_api_key(config_dir)
        settings = session.get(f"{client.base_url}/settings/main", timeout=8.0)
        if settings.status_code == 200:
            key = _find_api_key(settings.json())
            if key:
                return key
    except Exception as exc:
        logger.debug("Seerr API key discovery error: %s", exc)
    return read_seerr_api_key(config_dir)


class SeerrClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 5055, api_key: Optional[str] = None):
        self.base_url = f"http://{host}:{port}/api/v1"
        self.api_key = api_key

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-Api-Key"] = self.api_key
        return headers

    def connect_radarr(
        self,
        host: str = "127.0.0.1",
        port: int = 7878,
        api_key: str = "",
        root_folder: str = "/data/media/movies",
    ) -> bool:
        """Link Radarr instance into Seerr."""
        try:
            existing = requests.get(f"{self.base_url}/settings/radarr", headers=self._headers(), timeout=5.0)
            if existing.status_code == 200 and len(existing.json()) > 0:
                logger.info("Seerr Radarr integration already configured.")
                return True

            payload = {
                "name": "Radarr (AMM)",
                "hostname": host,
                "port": port,
                "apiKey": api_key,
                "useSsl": False,
                "baseUrl": "",
                "activeProfileId": 1,
                "activeProfileName": "Any",
                "activeDirectory": root_folder,
                "is4k": False,
                "isDefault": True,
            }
            resp = requests.post(f"{self.base_url}/settings/radarr", headers=self._headers(), json=payload, timeout=5.0)
            return resp.status_code in (200, 201)
        except Exception as exc:
            logger.debug("Seerr connect_radarr error: %s", exc)
            return False

    def connect_sonarr(
        self,
        host: str = "127.0.0.1",
        port: int = 8989,
        api_key: str = "",
        root_folder: str = "/data/media/tv",
    ) -> bool:
        """Link Sonarr instance into Seerr."""
        try:
            existing = requests.get(f"{self.base_url}/settings/sonarr", headers=self._headers(), timeout=5.0)
            if existing.status_code == 200 and len(existing.json()) > 0:
                logger.info("Seerr Sonarr integration already configured.")
                return True

            payload = {
                "name": "Sonarr (AMM)",
                "hostname": host,
                "port": port,
                "apiKey": api_key,
                "useSsl": False,
                "baseUrl": "",
                "activeProfileId": 1,
                "activeProfileName": "Any",
                "activeDirectory": root_folder,
                "is4k": False,
                "isDefault": True,
            }
            resp = requests.post(f"{self.base_url}/settings/sonarr", headers=self._headers(), json=payload, timeout=5.0)
            return resp.status_code in (200, 201)
        except Exception as exc:
            logger.debug("Seerr connect_sonarr error: %s", exc)
            return False

    def connect_jellyfin(
        self,
        host: str = "127.0.0.1",
        port: int = 8096,
        api_key: str = "",
    ) -> bool:
        """Link Jellyfin media server into Seerr."""
        try:
            payload = {
                "hostname": host,
                "port": port,
                "useSsl": False,
                "urlBase": "",
                "apiKey": api_key,
            }
            resp = requests.post(f"{self.base_url}/settings/jellyfin", headers=self._headers(), json=payload, timeout=5.0)
            return resp.status_code in (200, 201)
        except Exception as exc:
            logger.debug("Seerr connect_jellyfin error: %s", exc)
            return False

    def connect_plex(
        self,
        host: str = "127.0.0.1",
        port: int = 32400,
    ) -> bool:
        """Link Plex Media Server into Seerr."""
        try:
            payload = {
                "ip": host,
                "port": port,
                "useSsl": False,
            }
            resp = requests.post(
                f"{self.base_url}/settings/plex",
                headers=self._headers(),
                json=payload,
                timeout=5.0,
            )
            return resp.status_code in (200, 201)
        except Exception as exc:
            logger.debug("Seerr connect_plex error: %s", exc)
            return False

    def setup_local_admin(self, email: str, username: str, password: str) -> bool:
        """Create the first Seerr local admin when email and password are known."""
        email = (email or "").strip()
        username = (username or "").strip() or "admin"
        if not email or not password:
            return False
        payload = {"email": email, "username": username, "password": password}
        try:
            init = requests.post(
                f"{self.base_url}/settings/initialize",
                headers=self._headers(),
                json=payload,
                timeout=8.0,
            )
            if init.status_code in (200, 201):
                logger.info("Initialized Seerr local admin '%s'.", username)
                return True
            local = requests.post(
                f"{self.base_url}/auth/local",
                headers=self._headers(),
                json=payload,
                timeout=8.0,
            )
            if local.status_code in (200, 201, 409):
                logger.info("Seerr local auth ready for '%s'.", username)
                return True
            return False
        except Exception as exc:
            logger.debug("Seerr setup_local_admin error: %s", exc)
            return False
