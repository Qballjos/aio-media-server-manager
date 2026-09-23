"""
core/integrations/radarr.py — Radarr v3 REST API Client.

Registers download clients (SABnzbd and qBittorrent), sets root media folders,
and applies sensible default movie naming templates.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
import requests

logger = logging.getLogger(__name__)


class RadarrClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 7878, api_key: Optional[str] = None):
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
            logger.debug("Radarr get_root_folders error: %s", exc)
        return []

    def add_root_folder(self, path: str = "/data/media/movies") -> bool:
        folders = self.get_root_folders()
        if any(f.get("path") == path for f in folders):
            logger.info("Radarr root folder '%s' already configured.", path)
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
                logger.info("Configured Radarr root folder: %s", path)
            return success
        except Exception as exc:
            logger.debug("Radarr add_root_folder error: %s", exc)
            return False

    def get_download_clients(self) -> list[dict[str, Any]]:
        try:
            resp = requests.get(f"{self.base_url}/downloadclient", headers=self._headers(), timeout=5.0)
            if resp.status_code == 200:
                return resp.json()
        except Exception as exc:
            logger.debug("Radarr get_download_clients error: %s", exc)
        return []

    def add_sabnzbd_client(self, host: str = "127.0.0.1", port: int = 8080, api_key: str = "", category: str = "radarr") -> bool:
        clients = self.get_download_clients()
        if any(c.get("implementation") == "Sabnzbd" for c in clients):
            logger.info("Radarr SABnzbd download client already exists.")
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
                {"name": "movieCategory", "value": category},
                {"name": "useSsl", "value": False},
            ],
        }
        try:
            resp = requests.post(f"{self.base_url}/downloadclient", headers=self._headers(), json=payload, timeout=8.0)
            if resp.status_code in (200, 201):
                return True
            logger.warning("Radarr add SABnzbd failed (%s): %s", resp.status_code, resp.text[:500])
            return False
        except Exception as exc:
            logger.debug("Radarr add SABnzbd error: %s", exc)
            return False

    def add_qbittorrent_client(self, host: str = "127.0.0.1", port: int = 8085, username: str = "admin", password: str = "adminadmin", category: str = "radarr") -> bool:
        clients = self.get_download_clients()
        if any(c.get("implementation") == "QBittorrent" for c in clients):
            logger.info("Radarr qBittorrent download client already exists.")
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
                {"name": "movieCategory", "value": category},
                {"name": "useSsl", "value": False},
            ],
        }
        try:
            resp = requests.post(f"{self.base_url}/downloadclient", headers=self._headers(), json=payload, timeout=8.0)
            if resp.status_code in (200, 201):
                return True
            logger.warning("Radarr add qBittorrent failed (%s): %s", resp.status_code, resp.text[:500])
            return False
        except Exception as exc:
            logger.debug("Radarr add qBittorrent error: %s", exc)
            return False

    def add_nzbget_client(
        self,
        host: str = "127.0.0.1",
        port: int = 6789,
        username: str = "nzbget",
        password: str = "tegbzn6789",
        category: str = "radarr",
    ) -> bool:
        clients = self.get_download_clients()
        if any(c.get("implementation") == "Nzbget" for c in clients):
            logger.info("Radarr NZBGet download client already exists.")
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
                {"name": "movieCategory", "value": category},
                {"name": "useSsl", "value": False},
            ],
        }
        try:
            resp = requests.post(
                f"{self.base_url}/downloadclient",
                headers=self._headers(),
                json=payload,
                timeout=8.0,
            )
            if resp.status_code in (200, 201):
                return True
            logger.warning("Radarr add NZBGet failed (%s): %s", resp.status_code, resp.text[:500])
            return False
        except Exception as exc:
            logger.debug("Radarr add NZBGet error: %s", exc)
            return False

    def configure_naming_defaults(self) -> bool:
        """Set standard movie naming format."""
        try:
            resp = requests.get(f"{self.base_url}/config/naming", headers=self._headers(), timeout=5.0)
            if resp.status_code != 200:
                return False
            cfg = resp.json()
            cfg["renameMovies"] = True
            cfg["standardMovieFormat"] = "{Movie CleanTitle} ({Release Year}) [imdbid-{ImdbId}] - [{Quality Full}]"
            put_resp = requests.put(f"{self.base_url}/config/naming", headers=self._headers(), json=cfg, timeout=5.0)
            return put_resp.status_code in (200, 202)
        except Exception as exc:
            logger.debug("Radarr configure_naming_defaults error: %s", exc)
            return False
