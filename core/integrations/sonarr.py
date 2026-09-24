"""
core/integrations/sonarr.py — Sonarr v3 REST API Client.

Registers download clients (SABnzbd and qBittorrent), sets root media folders,
and applies sensible default episode naming templates.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
import requests

from core.integrations.arr_app import post_servarr_download_client, sabnzbd_download_client_fields

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

    def add_sabnzbd_client(
        self,
        host: str = "127.0.0.1",
        port: int = 8085,
        api_key: str = "",
        category: str = "sonarr",
        username: str = "",
        password: str = "",
    ) -> bool:
        clients = self.get_download_clients()
        if any(c.get("implementation") == "Sabnzbd" for c in clients):
            logger.info("Sonarr SABnzbd download client already exists.")
            return True
        return self._post_download_client(
            "SABnzbd",
            {
                "name": "SABnzbd (AMM)",
                "implementation": "Sabnzbd",
                "configContract": "SabnzbdSettings",
                "fields": sabnzbd_download_client_fields(
                    host=host,
                    port=port,
                    api_key=api_key,
                    category=category,
                    username=username,
                    password=password,
                ),
            },
        )

    def add_qbittorrent_client(self, host: str = "127.0.0.1", port: int = 8081, username: str = "admin", password: str = "adminadmin", category: str = "sonarr") -> bool:
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
        return self._post_download_client("qBittorrent", payload)

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
        return self._post_download_client("NZBGet", payload)

    def _post_download_client(self, label: str, payload: dict[str, Any]) -> bool:
        return post_servarr_download_client(
            self.base_url,
            self._headers(),
            name=str(payload.get("name") or label),
            implementation=str(payload.get("implementation") or ""),
            config_contract=str(payload.get("configContract") or ""),
            fields=list(payload.get("fields") or []),
            label="Sonarr",
        )

    def configure_naming_defaults(self) -> bool:
        """Set Servarr episode naming tokens (not Python format strings)."""
        try:
            resp = requests.get(f"{self.base_url}/config/naming", headers=self._headers(), timeout=5.0)
            if resp.status_code != 200:
                return False
            cfg = resp.json()
            cfg["renameEpisodes"] = True
            cfg["standardEpisodeFormat"] = (
                "{Series Title} - S{season:00}E{episode:00} - {Episode Title} [{Quality Full}]"
            )
            cfg["dailyEpisodeFormat"] = "{Series Title} - {Air-Date} - {Episode Title} [{Quality Full}]"
            cfg["animeEpisodeFormat"] = (
                "{Series Title} - S{season:00}E{episode:00} - {Episode Title} [{Quality Full}]"
            )
            cfg["seasonFolderFormat"] = "Season {season:00}"
            cfg["multiEpisodeStyle"] = 0
            put_resp = requests.put(f"{self.base_url}/config/naming", headers=self._headers(), json=cfg, timeout=5.0)
            if put_resp.status_code in (200, 202):
                return True
            logger.warning("Sonarr naming update failed (%s): %s", put_resp.status_code, put_resp.text[:500])
            return False
        except Exception as exc:
            logger.debug("Sonarr configure_naming_defaults error: %s", exc)
            return False
