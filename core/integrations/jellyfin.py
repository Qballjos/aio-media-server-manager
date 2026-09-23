"""Jellyfin REST helpers for libraries and transcoding temp path."""

from __future__ import annotations

import logging
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)


class JellyfinClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 8096, api_key: Optional[str] = None) -> None:
        self.base_url = f"http://{host}:{port}"
        self.api_key = api_key

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-Emby-Token"] = self.api_key
            headers["X-MediaBrowser-Token"] = self.api_key
        return headers

    def list_virtual_folders(self) -> list[dict[str, Any]]:
        try:
            resp = requests.get(
                f"{self.base_url}/Library/VirtualFolders",
                headers=self._headers(),
                timeout=5.0,
            )
            if resp.status_code == 200:
                data = resp.json()
                return data if isinstance(data, list) else []
        except Exception as exc:
            logger.debug("Jellyfin list_virtual_folders error: %s", exc)
        return []

    def add_media_library(self, name: str, collection_type: str, path: str) -> bool:
        folders = self.list_virtual_folders()
        for folder in folders:
            locations = folder.get("Locations") or folder.get("locations") or []
            names = [folder.get("Name"), folder.get("name")]
            if name in names:
                logger.info("Jellyfin library '%s' already exists.", name)
                return True
            for location in locations:
                loc = location.get("Path") if isinstance(location, dict) else location
                if loc == path:
                    logger.info("Jellyfin library path '%s' already exists.", path)
                    return True
        try:
            resp = requests.post(
                f"{self.base_url}/Library/VirtualFolders",
                headers=self._headers(),
                params={
                    "name": name,
                    "collectionType": collection_type,
                    "refreshLibrary": "true",
                },
                json={"LibraryOptions": {"PathInfos": [{"Path": path}]}},
                timeout=8.0,
            )
            if resp.status_code in (200, 204):
                return True
            retry = requests.post(
                f"{self.base_url}/Library/VirtualFolders",
                headers=self._headers(),
                params={
                    "name": name,
                    "collectionType": collection_type,
                    "paths": path,
                    "refreshLibrary": "true",
                },
                timeout=8.0,
            )
            return retry.status_code in (200, 204)
        except Exception as exc:
            logger.debug("Jellyfin add_media_library error: %s", exc)
            return False

    def set_transcoding_temp_path(self, path: str) -> bool:
        try:
            resp = requests.get(
                f"{self.base_url}/System/Configuration",
                headers=self._headers(),
                timeout=5.0,
            )
            if resp.status_code != 200:
                return False
            cfg = resp.json()
            if not isinstance(cfg, dict):
                return False
            cfg["TranscodingTempPath"] = path
            put = requests.post(
                f"{self.base_url}/System/Configuration",
                headers=self._headers(),
                json=cfg,
                timeout=5.0,
            )
            return put.status_code in (200, 204)
        except Exception as exc:
            logger.debug("Jellyfin set_transcoding_temp_path error: %s", exc)
            return False

    def ensure_local_admin(self, username: str, password: str) -> bool:
        """Create or align a local Jellyfin user with the manager login."""
        try:
            startup = requests.get(f"{self.base_url}/Startup/User", timeout=5.0)
            if startup.status_code == 200:
                created = requests.post(
                    f"{self.base_url}/Startup/User",
                    json={"Name": username, "Password": password},
                    timeout=8.0,
                )
                if created.status_code in (200, 204):
                    requests.post(f"{self.base_url}/Startup/Complete", timeout=8.0)
                    return True
        except Exception as exc:
            logger.debug("Jellyfin startup user error: %s", exc)

        try:
            resp = requests.get(f"{self.base_url}/Users", headers=self._headers(), timeout=5.0)
            if resp.status_code != 200:
                return False
            users = resp.json()
            if not isinstance(users, list):
                return False
            match = next(
                (
                    user
                    for user in users
                    if isinstance(user, dict) and str(user.get("Name") or "").lower() == username.lower()
                ),
                None,
            )
            if match and match.get("Id"):
                pw = requests.post(
                    f"{self.base_url}/Users/{match['Id']}/Password",
                    headers=self._headers(),
                    json={"CurrentPw": "", "NewPw": password, "ResetPassword": False},
                    timeout=8.0,
                )
                return pw.status_code in (200, 204)
            created = requests.post(
                f"{self.base_url}/Users/New",
                headers=self._headers(),
                json={"Name": username, "Password": password},
                timeout=8.0,
            )
            return created.status_code in (200, 204)
        except Exception as exc:
            logger.debug("Jellyfin ensure_local_admin error: %s", exc)
            return False
