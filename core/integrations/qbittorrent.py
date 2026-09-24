"""
core/integrations/qbittorrent.py — qBittorrent WebUI API Client.

Configures categories (e.g. 'sonarr', 'radarr') with specific save paths
to separate and route BitTorrent downloads.
"""

from __future__ import annotations

import logging
import time
from typing import Any
import json
import requests

from core.crypto import secret_store
from core.shared_credentials import shared_admin_credentials
from applications.qbittorrent.vuetorrent import alternative_ui_root
from applications.qbittorrent.webui import ensure_webui_localhost_access

logger = logging.getLogger(__name__)


def _persist_webui(config_dir, username: str, password: str) -> None:
    ensure_webui_localhost_access(
        config_dir,
        username=username,
        password=password,
        alternative_ui_root=alternative_ui_root(config_dir),
    )


def target_webui_credentials() -> tuple[str, str]:
    """Manager login unless the operator set a distinct qBittorrent user and password."""
    shared = shared_admin_credentials()
    username = (secret_store.get_secret("qbittorrent_username") or "").strip()
    password = secret_store.get_secret("qbittorrent_password") or ""
    if shared:
        if not username or username == "admin":
            username = shared[0]
        if not password:
            password = shared[1]
        return username, password
    if username and password:
        return username, password
    return "admin", "adminadmin"


def qbittorrent_credentials() -> tuple[str, str]:
    return target_webui_credentials()


class QBittorrentClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 8081, username: str | None = None, password: str | None = None):
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

    def app_accessible(self) -> bool:
        try:
            resp = self.session.get(f"{self.base_url}/app/version", timeout=5.0)
            return resp.status_code == 200
        except Exception:
            return False

    def set_webui_login(self, username: str, password: str) -> bool:
        """Set the WebUI username and password to the shared manager login."""
        try:
            payload = json.dumps(
                {
                    "web_ui_username": username,
                    "web_ui_password": password,
                    "username": username,
                    "password": password,
                }
            )
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


def apply_qbittorrent_webui_login(config_dir, port: int, *, restart_if_needed: bool = True) -> bool:
    """Persist the manager (or wizard) WebUI login via API, then conf + restart if needed."""
    username, password = target_webui_credentials()
    if not username or not password:
        return False
    secret_store.save_secret("qbittorrent_username", username)
    secret_store.save_secret("qbittorrent_password", password)

    client = QBittorrentClient(port=port, username=username, password=password)
    if (client.login() or client.app_accessible()) and client.set_webui_login(username, password):
        _persist_webui(config_dir, username=username, password=password)
        return True
    if not restart_if_needed:
        _persist_webui(config_dir, username=username, password=password)
        return False
    if not _rewrite_login_and_restart(config_dir, username, password):
        _persist_webui(config_dir, username=username, password=password)
        return False
    time.sleep(2)
    verify = QBittorrentClient(port=port, username=username, password=password)
    if verify.login():
        verify.set_webui_login(username, password)
        return True
    return verify.app_accessible()


def _rewrite_login_and_restart(config_dir, username: str, password: str) -> bool:
    from applications.catalog import ApplicationCatalog
    from core.settings import settings
    from core.supervisor import ProcessSupervisor

    catalog = ApplicationCatalog()
    if not catalog.has("qbittorrent"):
        _persist_webui(config_dir, username=username, password=password)
        return False
    plugin = catalog.get("qbittorrent")
    supervisor = ProcessSupervisor.get()

    async def _cycle() -> None:
        if supervisor.status("qbittorrent").value == "running":
            await supervisor.stop("qbittorrent")
        _persist_webui(plugin.config_dir, username=username, password=password)
        await supervisor.start(
            name="qbittorrent",
            cmd=plugin.start_command(),
            cwd=plugin.working_directory(),
            env=plugin.extra_env(),
            log_dir=settings.config_dir / "logs",
        )

    try:
        supervisor.run_coroutine_sync(_cycle(), timeout=90.0)
        return True
    except Exception as exc:
        logger.warning("Could not restart qBittorrent after writing WebUI login: %s", exc)
        _persist_webui(config_dir, username=username, password=password)
        return False
