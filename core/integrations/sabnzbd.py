"""
core/integrations/sabnzbd.py — SABnzbd REST API Client.

Configures categories (e.g. 'sonarr' with relative dir 'tv', 'radarr' with 'movies')
to ensure completed Usenet downloads are placed into expected folders.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

_JUNK_SERVER_NAMES = frozenset(
    {"host", "port", "username", "password", "connections", "ssl", "enable", "displayname", "name"}
)

_INI_KEY = re.compile(r"(?im)^api_key\s*=\s*[\"']?([0-9a-zA-Z]{16,})[\"']?")
_INI_USER = re.compile(r"(?im)^username\s*=\s*[\"']?([^\"'\n#]*?)[\"']?\s*$")
_INI_PASS = re.compile(r"(?im)^password\s*=\s*[\"']?([^\"'\n#]*?)[\"']?\s*$")


def read_sabnzbd_ini(config_dir: Path | None) -> dict[str, str]:
    """Read API key and login from sabnzbd.ini (quoted or plain)."""
    result = {"api_key": "", "username": "", "password": ""}
    if not config_dir:
        return result
    path = Path(config_dir) / "sabnzbd.ini"
    if not path.is_file():
        return result
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return result
    key = _INI_KEY.search(text)
    if key:
        result["api_key"] = key.group(1).strip()
    user = _INI_USER.search(text)
    if user:
        result["username"] = user.group(1).strip()
    password = _INI_PASS.search(text)
    if password:
        result["password"] = password.group(1).strip()
    return result


class SABnzbdClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 8085, api_key: Optional[str] = None):
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
        raw = data.get("categories", [])
        if isinstance(raw, dict):
            raw = raw.get("categories") or raw.get("value") or []
        if not isinstance(raw, list):
            return []
        return [str(item).strip() for item in raw if str(item).strip()]

    def has_category(self, name: str) -> bool:
        want = (name or "").strip().lower()
        if not want:
            return False
        return want in {item.lower() for item in self.get_categories() if item not in {"*", ""}}

    def add_category(self, name: str, dir_path: str = "") -> bool:
        """Create or update a category (SABnzbd 5: set_config on the categories section)."""
        want = (name or "").strip().lower()
        if not want:
            return False
        if self.has_category(want):
            logger.info("SABnzbd category '%s' already exists.", want)
            return True
        params = {"section": "categories", "name": want, "dir": dir_path or ""}
        res = self._request("set_config", params)
        if self.has_category(want):
            logger.info("Added SABnzbd category '%s' -> '%s'", want, dir_path)
            return True
        logger.warning(
            "SABnzbd category '%s' was not created (%s).",
            want,
            res.get("error") or res.get("status"),
        )
        return False

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
        """Add or update a single Usenet server (one set_config, never per-field rows)."""
        host = (host or "").strip()
        if not host:
            return False
        name = (displayname or host).strip()
        self._remove_accidental_servers()
        if self._has_news_server(host):
            logger.info("SABnzbd already has Usenet server for '%s'.", host)
            return True
        # Do not pass `keyword` — SABnzbd treats it as the server identity.
        res = self._request(
            "set_config",
            {
                "section": "servers",
                "name": name,
                "host": host,
                "port": str(int(port) or 563),
                "username": username or "",
                "password": password or "",
                "connections": str(max(1, int(connections) or 8)),
                "ssl": "1" if ssl else "0",
                "enable": "1",
                "displayname": name,
            },
        )
        ok = bool(res.get("status", False)) or self._has_news_server(host)
        if ok:
            logger.info("Configured SABnzbd Usenet server '%s'.", name)
        else:
            logger.warning("SABnzbd Usenet server '%s' was not saved (%s).", name, res.get("error") or res)
        return ok

    def list_servers(self) -> list[dict[str, Any]]:
        data = self._request("get_config", {"section": "servers"})
        rows = data.get("config")
        if isinstance(rows, dict):
            rows = rows.get("servers")
        if rows is None:
            rows = data.get("servers")
        if not isinstance(rows, list):
            return []
        return [item for item in rows if isinstance(item, dict)]

    def _has_news_server(self, host: str) -> bool:
        want = host.strip().lower()
        for item in self.list_servers():
            if str(item.get("host") or "").strip().lower() == want:
                return True
            if str(item.get("name") or "").strip().lower() == want:
                return True
        return False

    def _remove_accidental_servers(self) -> None:
        """Drop servers created by the old per-keyword set_config loop (named host, port, ssl, …)."""
        for item in self.list_servers():
            ident = str(item.get("name") or item.get("host") or "").strip().lower()
            if ident not in _JUNK_SERVER_NAMES:
                continue
            self._request("del_config", {"section": "servers", "keyword": ident})
            logger.info("Removed extra SABnzbd server entry '%s'.", ident)


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
        "helpful_warnings = 0",
        f"complete_dir = {_ini_value(complete_dir)}",
        f"download_dir = {_ini_value(incomplete_dir)}",
        f"api_key = {key}",
        f"nzb_key = {secrets.token_hex(16)}",
        "host_whitelist = localhost,127.0.0.1,::1",
        "local_ranges = 127.0.0.1/32,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16",
    ]
    if username:
        lines.append(f"username = {_ini_value(username)}")
    if password:
        lines.append(f"password = {_ini_value(password)}")
    lines.extend(
        [
            "",
            "[categories]",
            "[[sonarr]]",
            "order = 0",
            "pp = 3",
            "priority = 0",
            "dir = tv",
            "[[radarr]]",
            "order = 1",
            "pp = 3",
            "priority = 0",
            "dir = movies",
            "[[anime]]",
            "order = 2",
            "pp = 3",
            "priority = 0",
            "dir = anime",
            "[[lidarr]]",
            "order = 3",
            "pp = 3",
            "priority = 0",
            "dir = music",
        ]
    )
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
