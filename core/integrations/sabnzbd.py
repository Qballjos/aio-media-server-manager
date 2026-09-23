"""
core/integrations/sabnzbd.py — SABnzbd REST API Client.

Configures categories (e.g. 'sonarr' with relative dir 'tv', 'radarr' with 'movies')
to ensure completed Usenet downloads are placed into expected folders.
"""

from __future__ import annotations

import logging
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
