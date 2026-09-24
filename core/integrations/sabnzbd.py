"""
core/integrations/sabnzbd.py — SABnzbd REST API Client.

Configures categories (e.g. 'sonarr' with relative dir 'tv', 'radarr' with 'movies')
to ensure completed Usenet downloads are placed into expected folders.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)


class SABnzbdClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 8080, api_key: Optional[str] = None):
        self.base_url = f"http://{host}:{port}/api"
        self.api_key = api_key

    def _request(self, mode: str, extra_params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        params = {"mode": mode, "output": "json"}
        if self.api_key:
            params["apikey"] = self.api_key
        if extra_params:
            params.update(extra_params)

        try:
            resp = requests.get(self.base_url, params=params, timeout=5.0)
            resp.raise_for_status()
            return resp.json() if resp.content else {}
        except Exception as exc:
            logger.debug("SABnzbd API %s request error: %s", mode, exc)
            return {"status": False, "error": str(exc)}

    def get_categories(self) -> list[str]:
        """Fetch list of existing category names."""
        data = self._request("get_cats")
        return data.get("categories", [])

    def add_category(self, name: str, dir_path: str = "") -> bool:
        """Create or update category if missing."""
        cats = self.get_categories()
        if name in cats:
            logger.info("SABnzbd category '%s' already exists.", name)
            return True

        res = self._request("addcategory", {"name": name, "dir": dir_path})
        success = bool(res.get("status", False))
        if success:
            logger.info("Added SABnzbd category '%s' -> '%s'", name, dir_path)
        return success

    def set_folders(self, complete_dir: str, incomplete_dir: str) -> bool:
        """Point SABnzbd at the appliance complete and incomplete directories."""
        complete_ok = self._request(
            "set_config",
            {"section": "misc", "keyword": "complete_dir", "value": complete_dir},
        )
        incomplete_ok = self._request(
            "set_config",
            {"section": "misc", "keyword": "download_dir", "value": incomplete_dir},
        )
        return bool(complete_ok.get("status", False)) and bool(incomplete_ok.get("status", False))

    def set_login(self, username: str, password: str) -> bool:
        user_ok = self._request("set_config", {"section": "misc", "keyword": "username", "value": username})
        pass_ok = self._request("set_config", {"section": "misc", "keyword": "password", "value": password})
        return bool(user_ok.get("status", False)) and bool(pass_ok.get("status", False))

    def add_news_server(
        self,
        *,
        host: str,
        port: int = 563,
        username: str = "",
        password: str = "",
        ssl: bool = True,
        connections: int = 8,
        displayname: str = "",
    ) -> bool:
        """Add or update a Usenet news server in SABnzbd."""
        host = (host or "").strip()
        if not host:
            return False
        name = (displayname or host).strip()
        fields = {
            "host": host,
            "port": str(int(port) or 563),
            "username": username or "",
            "password": password or "",
            "connections": str(max(1, int(connections) or 8)),
            "ssl": "1" if ssl else "0",
            "enable": "1",
            "displayname": name,
        }
        added = self._request("addserver", {"name": name, **fields})
        if bool(added.get("status", False)):
            logger.info("Added SABnzbd Usenet server '%s'.", name)
            return True
        # SABnzbd 5 prefers set_config on the servers section.
        created = self._request(
            "set_config",
            {"section": "servers", "keyword": "host", "value": host, "name": name},
        )
        ok = bool(created.get("status", False)) or bool(added.get("status", False))
        for keyword, value in fields.items():
            res = self._request(
                "set_config",
                {"section": "servers", "keyword": keyword, "value": value, "name": name},
            )
            ok = bool(res.get("status", False)) or ok
        if ok:
            logger.info("Configured SABnzbd Usenet server '%s'.", name)
        return ok


def _ini_value(value: object) -> str:
    text = str(value)
    if any(ch in text for ch in " #\t=\"'[]"):
        return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return text


def write_bootstrap_ini(
    path: Path,
    *,
    port: int,
    complete_dir: str,
    incomplete_dir: str,
    username: str = "",
    password: str = "",
    usenet: dict | None = None,
    api_key: str | None = None,
) -> Path:
    """Write a first-start sabnzbd.ini so the API and Usenet server exist before the web wizard."""
    import secrets

    path = Path(path)
    if path.exists():
        return path
    key = (api_key or secrets.token_hex(16)).strip()
    lines = [
        "[misc]",
        f"host = 0.0.0.0",
        f"port = {int(port) or 8085}",
        "auto_browser = 0",
        "check_new_rel = 0",
        f"complete_dir = {_ini_value(complete_dir)}",
        f"download_dir = {_ini_value(incomplete_dir)}",
        f"api_key = {key}",
        f"nzb_key = {secrets.token_hex(16)}",
        "host_whitelist = localhost,127.0.0.1",
        "local_ranges = 127.0.0.1/32,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16",
    ]
    if username:
        lines.append(f"username = {_ini_value(username)}")
    if password:
        lines.append(f"password = {_ini_value(password)}")
    server = usenet or {}
    host = str(server.get("host") or "").strip()
    if host:
        name = host
        ssl = "1" if server.get("ssl", True) else "0"
        connections = max(1, int(server.get("connections") or 8))
        port_n = int(server.get("port") or 563)
        lines.extend(
            [
                "",
                "[servers]",
                f"[[{name}]]",
                "enable = 1",
                f"name = {_ini_value(name)}",
                f"displayname = {_ini_value(name)}",
                f"host = {_ini_value(host)}",
                f"port = {port_n}",
                f"username = {_ini_value(server.get('username') or '')}",
                f"password = {_ini_value(server.get('password') or '')}",
                f"connections = {connections}",
                f"ssl = {ssl}",
                "ssl_verify = 2",
                "priority = 0",
            ]
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
