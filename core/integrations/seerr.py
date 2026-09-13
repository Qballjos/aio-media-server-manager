"""
core/integrations/seerr.py — Seerr (Overseerr/Jellyseerr) REST API Client.

Connects Seerr to media servers (Jellyfin/Plex) and automation apps (Sonarr/Radarr)
so user media requests automatically route to the appropriate downloader and library.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
import requests

logger = logging.getLogger(__name__)


class SeerrClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 5055, api_key: Optional[str] = None):
        self.base_url = f"http://{host}:{port}/api/v1"
        self.api_key = api_key

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-Api-Key"] = self.api_key
        return headers

    def connect_radarr(
        self,
        host: str = "127.0.0.1",
        port: int = 7878,
        api_key: str = "",
        root_folder: str = "/data/media/movies",
    ) -> bool:
        """Link Radarr instance into Seerr."""
        try:
            existing = requests.get(f"{self.base_url}/settings/radarr", headers=self._headers(), timeout=5.0)
            if existing.status_code == 200 and len(existing.json()) > 0:
                logger.info("Seerr Radarr integration already configured.")
                return True

            payload = {
                "name": "Radarr (AMM)",
                "hostname": host,
                "port": port,
                "apiKey": api_key,
                "useSsl": False,
                "baseUrl": "",
                "activeProfileId": 1,
                "activeProfileName": "Any",
                "activeDirectory": root_folder,
                "is4k": False,
                "isDefault": True,
            }
            resp = requests.post(f"{self.base_url}/settings/radarr", headers=self._headers(), json=payload, timeout=5.0)
            return resp.status_code in (200, 201)
        except Exception as exc:
            logger.debug("Seerr connect_radarr error: %s", exc)
            return False

    def connect_sonarr(
        self,
        host: str = "127.0.0.1",
        port: int = 8989,
        api_key: str = "",
        root_folder: str = "/data/media/tv",
    ) -> bool:
        """Link Sonarr instance into Seerr."""
        try:
            existing = requests.get(f"{self.base_url}/settings/sonarr", headers=self._headers(), timeout=5.0)
            if existing.status_code == 200 and len(existing.json()) > 0:
                logger.info("Seerr Sonarr integration already configured.")
                return True

            payload = {
                "name": "Sonarr (AMM)",
                "hostname": host,
                "port": port,
                "apiKey": api_key,
                "useSsl": False,
                "baseUrl": "",
                "activeProfileId": 1,
                "activeProfileName": "Any",
                "activeDirectory": root_folder,
                "is4k": False,
                "isDefault": True,
            }
            resp = requests.post(f"{self.base_url}/settings/sonarr", headers=self._headers(), json=payload, timeout=5.0)
            return resp.status_code in (200, 201)
        except Exception as exc:
            logger.debug("Seerr connect_sonarr error: %s", exc)
            return False

    def connect_jellyfin(
        self,
        host: str = "127.0.0.1",
        port: int = 8096,
        api_key: str = "",
    ) -> bool:
        """Link Jellyfin media server into Seerr."""
        try:
            payload = {
                "hostname": host,
                "port": port,
                "useSsl": False,
                "urlBase": "",
                "apiKey": api_key,
            }
            resp = requests.post(f"{self.base_url}/settings/jellyfin", headers=self._headers(), json=payload, timeout=5.0)
            return resp.status_code in (200, 201)
        except Exception as exc:
            logger.debug("Seerr connect_jellyfin error: %s", exc)
            return False
