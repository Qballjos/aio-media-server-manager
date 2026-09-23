"""
core/integrations/prowlarr.py — Prowlarr v1 REST API Client.

Registers Sonarr and Radarr as sync applications in Prowlarr,
so indexers configured in Prowlarr automatically push to Sonarr and Radarr.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
import requests

logger = logging.getLogger(__name__)


class ProwlarrClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 9696, api_key: Optional[str] = None):
        self.base_url = f"http://{host}:{port}/api/v1"
        self.host = host
        self.port = port
        self.api_key = api_key

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-Api-Key"] = self.api_key
        return headers

    def get_applications(self) -> list[dict[str, Any]]:
        try:
            resp = requests.get(f"{self.base_url}/applications", headers=self._headers(), timeout=5.0)
            if resp.status_code == 200:
                return resp.json()
        except Exception as exc:
            logger.debug("Prowlarr get_applications error: %s", exc)
        return []

    def sync_sonarr(self, sonarr_url: str = "http://127.0.0.1:8989", sonarr_api_key: str = "") -> bool:
        apps = self.get_applications()
        if any(a.get("implementation") == "Sonarr" for a in apps):
            logger.info("Prowlarr Sonarr sync application already registered.")
            return True

        prowlarr_url = f"http://{self.host}:{self.port}"
        payload = {
            "enable": True,
            "name": "Sonarr (AMM)",
            "syncLevel": "fullSync",
            "implementation": "Sonarr",
            "configContract": "SonarrSettings",
            "fields": [
                {"name": "prowlarrUrl", "value": prowlarr_url},
                {"name": "baseUrl", "value": sonarr_url},
                {"name": "apiKey", "value": sonarr_api_key},
                {"name": "syncCategories", "value": [5000, 5010, 5020, 5030, 5040, 5045, 5050]},
            ],
        }
        try:
            resp = requests.post(f"{self.base_url}/applications", headers=self._headers(), json=payload, timeout=5.0)
            return resp.status_code in (200, 201)
        except Exception as exc:
            logger.debug("Prowlarr sync_sonarr error: %s", exc)
            return False

    def sync_radarr(self, radarr_url: str = "http://127.0.0.1:7878", radarr_api_key: str = "") -> bool:
        apps = self.get_applications()
        if any(a.get("implementation") == "Radarr" for a in apps):
            logger.info("Prowlarr Radarr sync application already registered.")
            return True

        prowlarr_url = f"http://{self.host}:{self.port}"
        payload = {
            "enable": True,
            "name": "Radarr (AMM)",
            "syncLevel": "fullSync",
            "implementation": "Radarr",
            "configContract": "RadarrSettings",
            "fields": [
                {"name": "prowlarrUrl", "value": prowlarr_url},
                {"name": "baseUrl", "value": radarr_url},
                {"name": "apiKey", "value": radarr_api_key},
                {"name": "syncCategories", "value": [2000, 2010, 2020, 2030, 2040, 2045, 2050]},
            ],
        }
        try:
            resp = requests.post(f"{self.base_url}/applications", headers=self._headers(), json=payload, timeout=5.0)
            return resp.status_code in (200, 201)
        except Exception as exc:
            logger.debug("Prowlarr sync_radarr error: %s", exc)
            return False

    def sync_lidarr(self, lidarr_url: str = "http://127.0.0.1:8686", lidarr_api_key: str = "") -> bool:
        return self._sync_app(
            "Lidarr",
            "LidarrSettings",
            "Lidarr (AMM)",
            lidarr_url,
            lidarr_api_key,
            [3000, 3010, 3020, 3030, 3040],
        )

    def _sync_app(
        self,
        implementation: str,
        config_contract: str,
        name: str,
        base_url: str,
        api_key: str,
        categories: list[int],
    ) -> bool:
        apps = self.get_applications()
        if any(item.get("implementation") == implementation for item in apps):
            logger.info("Prowlarr %s sync application already registered.", implementation)
            return True
        payload = {
            "enable": True,
            "name": name,
            "syncLevel": "fullSync",
            "implementation": implementation,
            "configContract": config_contract,
            "fields": [
                {"name": "prowlarrUrl", "value": f"http://{self.host}:{self.port}"},
                {"name": "baseUrl", "value": base_url},
                {"name": "apiKey", "value": api_key},
                {"name": "syncCategories", "value": categories},
            ],
        }
        try:
            resp = requests.post(
                f"{self.base_url}/applications",
                headers=self._headers(),
                json=payload,
                timeout=5.0,
            )
            return resp.status_code in (200, 201)
        except Exception as exc:
            logger.debug("Prowlarr sync %s error: %s", implementation, exc)
            return False
