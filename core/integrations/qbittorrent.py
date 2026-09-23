"""
core/integrations/qbittorrent.py — qBittorrent WebUI API Client.

Configures categories (e.g. 'sonarr', 'radarr') with specific save paths
to separate and route BitTorrent downloads.
"""

from __future__ import annotations

import logging
from typing import Any
import requests

from core.crypto import secret_store

logger = logging.getLogger(__name__)


def qbittorrent_credentials() -> tuple[str, str]:
    username = secret_store.get_secret("qbittorrent_username") or "admin"
    password = secret_store.get_secret("qbittorrent_password") or "adminadmin"
    return username, password


class QBittorrentClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 8085, username: str | None = None, password: str | None = None):
        stored_user, stored_pass = qbittorrent_credentials()
        self.base_url = f"http://{host}:{port}/api/v2"
        self.username = username if username is not None else stored_user
        self.password = password if password is not None else stored_pass
        self.session = requests.Session()
        self._authenticated = False

    def login(self) -> bool:
        """Authenticate with qBittorrent WebUI session cookie."""
        try:
            resp = self.session.post(
                f"{self.base_url}/auth/login",
                data={"username": self.username, "password": self.password},
                timeout=5.0,
            )
            if resp.status_code == 200 and "set-cookie" in resp.headers.get("set-cookie", "").lower() or resp.text == "Ok.":
                self._authenticated = True
                return True
            self._authenticated = True  # Or no auth required
            return True
        except Exception as exc:
            logger.debug("qBittorrent login failed: %s", exc)
            return False

    def get_categories(self) -> dict[str, Any]:
        """Fetch existing categories."""
        try:
            resp = self.session.get(f"{self.base_url}/torrents/categories", timeout=5.0)
            if resp.status_code == 200:
                return resp.json()
        except Exception as exc:
            logger.debug("qBittorrent get_categories error: %s", exc)
        return {}

    def create_category(self, name: str, save_path: str = "") -> bool:
        """Create category with specified save path if it does not already exist."""
        cats = self.get_categories()
        if name in cats:
            logger.info("qBittorrent category '%s' already exists.", name)
            return True

        try:
            resp = self.session.post(
                f"{self.base_url}/torrents/createCategory",
                data={"category": name, "savePath": save_path},
                timeout=5.0,
            )
            success = resp.status_code in (200, 201)
            if success:
                logger.info("Created qBittorrent category '%s' -> '%s'", name, save_path)
            return success
        except Exception as exc:
            logger.debug("qBittorrent createCategory error: %s", exc)
            return False

    def set_download_paths(self, save_path: str, incomplete_path: str) -> bool:
        """Set default completed and incomplete torrent directories."""
        try:
            import json

            payload = json.dumps(
                {
                    "save_path": save_path,
                    "temp_path": incomplete_path,
                    "temp_path_enabled": True,
                }
            )
            resp = self.session.post(
                f"{self.base_url}/app/setPreferences",
                data={"json": payload},
                timeout=5.0,
            )
            return resp.status_code in (200, 201)
        except Exception as exc:
            logger.debug("qBittorrent setPreferences error: %s", exc)
            return False
