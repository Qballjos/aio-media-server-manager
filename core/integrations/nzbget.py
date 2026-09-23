"""NZBGet JSON-RPC client for category setup."""

from __future__ import annotations

import logging
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)


class NZBGetClient:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 6789,
        username: str = "nzbget",
        password: str = "tegbzn6789",
    ) -> None:
        self.url = f"http://{host}:{port}/jsonrpc"
        self.auth = (username, password)

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
