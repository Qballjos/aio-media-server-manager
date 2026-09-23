"""
core/integrations/sonarr.py — Sonarr v3 REST API Client.

Registers download clients (SABnzbd and qBittorrent), sets root media folders,
and applies sensible default episode naming templates.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
import requests

logger = logging.getLogger(__name__)


class SonarrClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 8989, api_key: Optional[str] = None):
        self.base_url = f"http://{host}:{port}/api/v3"
        self.api_key = api_key

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-Api-Key"] = self.api_key
        return headers

    def get_root_folders(self) -> list[dict[str, Any]]:
        try:
            resp = requests.get(f"{self.base_url}/rootfolder", headers=self._headers(), timeout=5.0)
            if resp.status_code == 200:
                return resp.json()
        except Exception as exc:
            logger.debug("Sonarr get_root_folders error: %s", exc)
        return []

    def add_root_folder(self, path: str = "/data/media/tv") -> bool:
        folders = self.get_root_folders()
        if any(f.get("path") == path for f in folders):
            logger.info("Sonarr root folder '%s' already configured.", path)
            return True

        try:
            resp = requests.post(
                f"{self.base_url}/rootfolder",
                headers=self._headers(),
                json={"path": path},
                timeout=5.0,
            )
            success = resp.status_code in (200, 201)
            if success:
                logger.info("Configured Sonarr root folder: %s", path)
            return success
        except Exception as exc:
            logger.debug("Sonarr add_root_folder error: %s", exc)
            return False

    def get_download_clients(self) -> list[dict[str, Any]]:
        try:
            resp = requests.get(f"{self.base_url}/downloadclient", headers=self._headers(), timeout=5.0)
            if resp.status_code == 200:
                return resp.json()
        except Exception as exc:
            logger.debug("Sonarr get_download_clients error: %s", exc)
        return []

    def add_sabnzbd_client(self, host: str = "127.0.0.1", port: int = 8080, api_key: str = "", category: str = "sonarr") -> bool:
        clients = self.get_download_clients()
        if any(c.get("implementation") == "Sabnzbd" for c in clients):
            logger.info("Sonarr SABnzbd download client already exists.")
            return True

        payload = {
            "enable": True,
            "name": "SABnzbd (AMM)",
            "implementation": "Sabnzbd",
            "configContract": "SabnzbdSettings",
            "fields": [
                {"name": "host", "value": host},
                {"name": "port", "value": port},
                {"name": "apiKey", "value": api_key},
                {"name": "tvCategory", "value": category},
                {"name": "useSsl", "value": False},
            ],
        }
        try:
            resp = requests.post(f"{self.base_url}/downloadclient", headers=self._headers(), json=payload, timeout=5.0)
            return resp.status_code in (200, 201)
        except Exception as exc:
            logger.debug("Sonarr add SABnzbd error: %s", exc)
            return False

    def add_qbittorrent_client(self, host: str = "127.0.0.1", port: int = 8085, username: str = "admin", password: str = "adminadmin", category: str = "sonarr") -> bool:
        clients = self.get_download_clients()
        if any(c.get("implementation") == "QBittorrent" for c in clients):
            logger.info("Sonarr qBittorrent download client already exists.")
            return True

        payload = {
            "enable": True,
            "name": "qBittorrent (AMM)",
            "implementation": "QBittorrent",
            "configContract": "QBittorrentSettings",
            "fields": [
                {"name": "host", "value": host},
                {"name": "port", "value": port},
                {"name": "username", "value": username},
                {"name": "password", "value": password},
                {"name": "tvCategory", "value": category},
                {"name": "useSsl", "value": False},
            ],
        }
        try:
            resp = requests.post(f"{self.base_url}/downloadclient", headers=self._headers(), json=payload, timeout=5.0)
            return resp.status_code in (200, 201)
        except Exception as exc:
            logger.debug("Sonarr add qBittorrent error: %s", exc)
            return False

    def add_nzbget_client(
        self,
        host: str = "127.0.0.1",
        port: int = 6789,
        username: str = "nzbget",
        password: str = "tegbzn6789",
        category: str = "sonarr",
    ) -> bool:
        clients = self.get_download_clients()
        if any(c.get("implementation") == "Nzbget" for c in clients):
            logger.info("Sonarr NZBGet download client already exists.")
            return True
        payload = {
            "enable": True,
            "name": "NZBGet (AMM)",
            "implementation": "Nzbget",
            "configContract": "NzbgetSettings",
            "fields": [
                {"name": "host", "value": host},
                {"name": "port", "value": port},
                {"name": "username", "value": username},
                {"name": "password", "value": password},
                {"name": "tvCategory", "value": category},
                {"name": "useSsl", "value": False},
            ],
        }
        try:
            resp = requests.post(
                f"{self.base_url}/downloadclient",
                headers=self._headers(),
                json=payload,
                timeout=5.0,
            )
            return resp.status_code in (200, 201)
        except Exception as exc:
            logger.debug("Sonarr add NZBGet error: %s", exc)
            return False

    def configure_naming_defaults(self) -> bool:
        """Set standard episode naming format."""
        try:
            resp = requests.get(f"{self.base_url}/config/naming", headers=self._headers(), timeout=5.0)
            if resp.status_code != 200:
                return False
            cfg = resp.json()
            cfg["renameEpisodes"] = True
            cfg["standardEpisodeFormat"] = "{Series Title} - S{season:02d}E{episode:02d} - {Episode Title} [{Quality Title}]"
            cfg["multiEpisodeStyle"] = 0
            put_resp = requests.put(f"{self.base_url}/config/naming", headers=self._headers(), json=cfg, timeout=5.0)
            return put_resp.status_code in (200, 202)
        except Exception as exc:
            logger.debug("Sonarr configure_naming_defaults error: %s", exc)
            return False
