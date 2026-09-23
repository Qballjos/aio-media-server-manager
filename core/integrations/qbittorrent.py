"""
core/integrations/qbittorrent.py — qBittorrent WebUI API Client.

Configures categories (e.g. 'sonarr', 'radarr') with specific save paths
to separate and route BitTorrent downloads.
"""

from __future__ import annotations

import logging
from typing import Any
import json
import requests

from core.crypto import secret_store
from core.shared_credentials import shared_admin_credentials

logger = logging.getLogger(__name__)


def qbittorrent_credentials() -> tuple[str, str]:
    username = secret_store.get_secret("qbittorrent_username")
    password = secret_store.get_secret("qbittorrent_password")
    if username and password:
        return username, password
    shared = shared_admin_credentials()
    if shared:
        return shared
    return "admin", "adminadmin"


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
        attempts: list[tuple[str, str]] = [(self.username, self.password)]
        shared = shared_admin_credentials()
        if shared:
            attempts.append(shared)
        # Localhost is often allowed with a blank password after LocalHostAuth=false.
        attempts.append((self.username or "admin", ""))
        if not secret_store.get_secret("qbittorrent_password"):
            attempts.append(("admin", ""))
        seen: set[tuple[str, str]] = set()
        for username, password in attempts:
            if (username, password) in seen:
                continue
            seen.add((username, password))
            try:
                resp = self.session.post(
                    f"{self.base_url}/auth/login",
                    data={"username": username, "password": password},
                    timeout=5.0,
                )
                cookie = resp.headers.get("Set-Cookie") or resp.headers.get("set-cookie") or ""
                if resp.status_code == 200 and (resp.text.strip() == "Ok." or "SID" in cookie):
                    self.username = username
                    self.password = password
                    self._authenticated = True
                    if username and password:
                        secret_store.save_secret("qbittorrent_username", username)
                        secret_store.save_secret("qbittorrent_password", password)
                    self.relax_local_auth()
                    return True
                if resp.status_code == 403:
                    logger.warning("qBittorrent login blocked (banned or CSRF); skipping further attempts")
                    return False
            except Exception as exc:
                logger.debug("qBittorrent login failed: %s", exc)
        return False

    def relax_local_auth(self) -> bool:
        """Bypass WebUI auth for 127.0.0.1 and clear any IP bans from wiring retries."""
        try:
            payload = json.dumps(
                {
                    "bypass_local_auth": True,
                    "web_ui_auth_subnet_whitelist_enabled": True,
                    "web_ui_auth_subnet_whitelist": "127.0.0.0/8, ::1",
                    "web_ui_csrf_protection_enabled": False,
                    "web_ui_host_header_validation_enabled": False,
                    "banned_IPs": "",
                }
            )
            resp = self.session.post(
                f"{self.base_url}/app/setPreferences",
                data={"json": payload},
                timeout=5.0,
            )
            return resp.status_code in (200, 201)
        except Exception as exc:
            logger.debug("qBittorrent relax_local_auth error: %s", exc)
            return False

    def set_webui_login(self, username: str, password: str) -> bool:
        """Set the WebUI username and password to the shared manager login."""
        try:
            payload = json.dumps({"web_ui_username": username, "web_ui_password": password})
            resp = self.session.post(
                f"{self.base_url}/app/setPreferences",
                data={"json": payload},
                timeout=5.0,
            )
            if resp.status_code in (200, 201):
                self.username = username
                self.password = password
                secret_store.save_secret("qbittorrent_username", username)
                secret_store.save_secret("qbittorrent_password", password)
                return True
        except Exception as exc:
            logger.debug("qBittorrent set_webui_login error: %s", exc)
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
