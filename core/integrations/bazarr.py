"""Bazarr API client — pair subtitle manager with Sonarr and Radarr."""

from __future__ import annotations

import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)


class BazarrClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 6767, api_key: Optional[str] = None):
        self.base_url = f"http://{host}:{port}/api"
        self.api_key = api_key

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-KEY"] = self.api_key
        return headers

    def pair_sonarr(self, sonarr_url: str, api_key: str) -> bool:
        return self._pair("sonarr", sonarr_url, api_key)

    def pair_radarr(self, radarr_url: str, api_key: str) -> bool:
        return self._pair("radarr", radarr_url, api_key)

    def _pair(self, kind: str, url: str, api_key: str) -> bool:
        payload = {
            "name": f"{kind.title()} (AMM)",
            "url": url,
            "apikey": api_key,
            "ssl": False,
        }
        endpoints = (
            f"{self.base_url}/{kind}",
            f"{self.base_url}/system/{kind}",
            f"{self.base_url}/{kind}s",
        )
        for endpoint in endpoints:
            try:
                resp = requests.post(endpoint, headers=self._headers(), json=payload, timeout=5.0)
                if resp.status_code in (200, 201, 204):
                    logger.info("Bazarr paired with %s via %s", kind, endpoint)
                    return True
            except Exception as exc:
                logger.debug("Bazarr pair %s via %s failed: %s", kind, endpoint, exc)
        return False

    def set_ui_auth(self, username: str, password: str, config_dir) -> bool:
        from pathlib import Path

        from core.integrations.local_auth import patch_bazarr_auth_yaml

        yaml_ok = False
        root = Path(config_dir)
        for yaml_path in (root / "config" / "config.yaml", root / "config.yaml"):
            yaml_ok = patch_bazarr_auth_yaml(yaml_path, username, password) or yaml_ok
        payload = {"auth": {"type": "form", "username": username, "password": password}}
        endpoints = (f"{self.base_url}/system/settings", f"{self.base_url}/settings")
        for endpoint in endpoints:
            try:
                resp = requests.post(endpoint, headers=self._headers(), json=payload, timeout=5.0)
                if resp.status_code in (200, 201, 204):
                    return True
            except Exception as exc:
                logger.debug("Bazarr set_ui_auth via %s failed: %s", endpoint, exc)
        return yaml_ok
