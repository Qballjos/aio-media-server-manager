"""NZBGet JSON-RPC client for category setup."""

from __future__ import annotations

import logging
from typing import Any, Optional

import requests

from core.shared_credentials import shared_admin_credentials

logger = logging.getLogger(__name__)


def nzbget_credentials() -> tuple[str, str]:
    shared = shared_admin_credentials()
    if shared:
        return shared
    return "nzbget", "tegbzn6789"


class NZBGetClient:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 6789,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        stored_user, stored_pass = nzbget_credentials()
        self.url = f"http://{host}:{port}/jsonrpc"
        self.username = username if username is not None else stored_user
        self.password = password if password is not None else stored_pass
        self.auth = (self.username, self.password)

    def set_login(self, username: str, password: str) -> bool:
        candidates = [(self.username, self.password), nzbget_credentials(), ("nzbget", "tegbzn6789")]
        seen: set[tuple[str, str]] = set()
        for user, pw in candidates:
            if (user, pw) in seen:
                continue
            seen.add((user, pw))
            self.auth = (user, pw)
            if self._call("version") is None:
                continue
            name_ok = self._call("configset", ["ControlUsername", username])
            pass_ok = self._call("configset", ["ControlPassword", password])
            if name_ok is not None and name_ok is not False and pass_ok is not None and pass_ok is not False:
                self.username = username
                self.password = password
                self.auth = (username, password)
                return True
        return False

    def _call(self, method: str, params: Optional[list[Any]] = None) -> Any:
        payload = {"jsonrpc": "2.0", "method": method, "params": params or [], "id": 1}
        try:
            resp = requests.post(self.url, json=payload, auth=self.auth, timeout=5.0)
            resp.raise_for_status()
            data = resp.json()
            return data.get("result")
        except Exception as exc:
            logger.debug("NZBGet %s error: %s", method, exc)
            return None

    def add_category(self, name: str, dest_dir: str = "") -> bool:
        config = self._call("config") or []
        names = [
            item.get("Value")
            for item in config
            if isinstance(item, dict) and str(item.get("Name", "")).endswith(".Name")
        ]
        if name in names:
            logger.info("NZBGet category '%s' already exists.", name)
            return True
        slot = 1
        existing_slots = {
            int(str(item.get("Name", "")).split("Category")[-1].split(".")[0])
            for item in config
            if isinstance(item, dict) and str(item.get("Name", "")).startswith("Category")
        }
        while slot in existing_slots:
            slot += 1
        ok_name = self._call("configset", [f"Category{slot}.Name", name])
        if dest_dir:
            self._call("configset", [f"Category{slot}.DestDir", dest_dir])
        return ok_name is not False and ok_name is not None

    def set_download_dirs(self, complete_dir: str, incomplete_dir: str) -> bool:
        dest = self._call("configset", ["DestDir", complete_dir])
        inter = self._call("configset", ["InterDir", incomplete_dir])
        return dest is not None and dest is not False and inter is not None and inter is not False

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
        host = (host or "").strip()
        if not host:
            return False
        name = (displayname or host).strip()
        encryption = "yes" if ssl else "no"
        pairs = [
            ("Server1.Active", "yes"),
            ("Server1.Name", name),
            ("Server1.Host", host),
            ("Server1.Port", str(int(port) or 563)),
            ("Server1.Username", username or ""),
            ("Server1.Password", password or ""),
            ("Server1.Encryption", encryption),
            ("Server1.Connections", str(max(1, int(connections) or 8))),
        ]
        ok = True
        for key, value in pairs:
            result = self._call("configset", [key, value])
            if result is None or result is False:
                ok = False
        self._call("save")
        if ok:
            logger.info("Configured NZBGet Usenet server '%s'.", name)
        return ok
