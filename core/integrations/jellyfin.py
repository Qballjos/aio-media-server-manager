"""Jellyfin REST helpers for libraries and transcoding temp path."""

from __future__ import annotations

import logging
import re
from typing import Any, Optional
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

_AUTH_HEADER = (
    'MediaBrowser Client="AIO Media Server Manager", Device="AMM", DeviceId="amm-jellyfin", Version="1.0.0", Token=""'
)


def jellyfin_auth_headers(api_key: Optional[str]) -> dict[str, str]:
    """Token in the Authorization header; Jellyfin 10.11 rejects legacy X-Emby-Token by default."""
    token = (api_key or "").strip().replace('"', "")
    auth = _AUTH_HEADER.replace('Token=""', f'Token="{token}"')
    headers = {
        "Content-Type": "application/json",
        "Authorization": auth,
        "X-Emby-Authorization": auth,
    }
    if token:
        headers["X-Emby-Token"] = token
        headers["X-MediaBrowser-Token"] = token
    return headers


def _jellyfin_listen_port(config_dir: Path | None, fallback: int = 8096) -> int:
    try:
        from core.app_prefs import load_app_ports

        stored = int(load_app_ports().get("jellyfin") or 0)
        if stored:
            return stored
    except Exception:
        pass
    if config_dir:
        xml = Path(config_dir) / "network.xml"
        if xml.is_file():
            try:
                match = re.search(r"<InternalHttpPort>(\d+)</InternalHttpPort>", xml.read_text(encoding="utf-8"))
                if match:
                    return int(match.group(1))
            except OSError:
                pass
    return int(fallback or 8096)


def discover_jellyfin_api_key(config_dir: Path | None = None, port: int = 8096) -> str:
    """Finish startup if needed, then log in with the shared manager account."""
    from core.shared_credentials import admin_email, shared_admin_credentials

    creds = shared_admin_credentials()
    if not creds:
        return ""
    username, password = creds
    if not username or not password:
        return ""
    client = JellyfinClient(port=_jellyfin_listen_port(config_dir, port))
    client.complete_startup(username, password)
    names = [username]
    email = (admin_email() or "").strip()
    if email:
        names.append(email)
        names.append(email.split("@", 1)[0])
    names.extend(client.public_usernames())
    seen: set[str] = set()
    for name in names:
        label = (name or "").strip()
        if not label or label.lower() in seen:
            continue
        seen.add(label.lower())
        token = client.authenticate(label, password)
        if token:
            return client.create_api_key("AIO-Media-Manager") or token
    return ""


class JellyfinClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 8096, api_key: Optional[str] = None) -> None:
        self.base_url = f"http://{host}:{port}"
        self.api_key = api_key

    def _headers(self) -> dict[str, str]:
        return jellyfin_auth_headers(self.api_key)

    def authenticate(self, username: str, password: str) -> str:
        """Return a session AccessToken for the local Jellyfin user."""
        headers = {
            "Content-Type": "application/json",
            "Authorization": _AUTH_HEADER,
            "X-Emby-Authorization": _AUTH_HEADER,
        }
        bodies = (
            {"Username": username, "Pw": password},
            {"Username": username, "Password": password},
        )
        for body in bodies:
            try:
                resp = requests.post(
                    f"{self.base_url}/Users/AuthenticateByName",
                    headers=headers,
                    json=body,
                    timeout=5.0,
                )
                if resp.status_code != 200:
                    logger.debug("Jellyfin authenticate failed (%s): %s", resp.status_code, resp.text[:300])
                    continue
                data = resp.json()
                token = str((data or {}).get("AccessToken") or "").strip()
                if token:
                    self.api_key = token
                    return token
            except Exception as exc:
                logger.debug("Jellyfin authenticate error: %s", exc)
        return ""

    def public_usernames(self) -> list[str]:
        try:
            resp = requests.get(f"{self.base_url}/Users/Public", timeout=4.0)
            if resp.status_code != 200:
                return []
            rows = resp.json()
            if not isinstance(rows, list):
                return []
            names: list[str] = []
            for row in rows:
                if isinstance(row, dict) and row.get("Name"):
                    names.append(str(row["Name"]))
            return names
        except Exception as exc:
            logger.debug("Jellyfin public users error: %s", exc)
            return []

    def complete_startup(self, username: str, password: str) -> bool:
        """Create the first admin if Jellyfin is still on the startup wizard."""
        try:
            info = requests.get(f"{self.base_url}/System/Info/Public", timeout=4.0)
            wizard_done = False
            if info.status_code == 200:
                payload = info.json() if info.content else {}
                if isinstance(payload, dict):
                    wizard_done = bool(payload.get("StartupWizardCompleted"))
            if wizard_done:
                return True
            requests.post(
                f"{self.base_url}/Startup/User",
                json={"Name": username, "Password": password},
                timeout=5.0,
            )
            done = requests.post(f"{self.base_url}/Startup/Complete", timeout=5.0)
            return done.status_code in (200, 204)
        except Exception as exc:
            logger.debug("Jellyfin complete_startup error: %s", exc)
            return False

    def create_api_key(self, app_name: str = "AIO-Media-Manager") -> str:
        if not self.api_key:
            return ""
        try:
            resp = requests.post(
                f"{self.base_url}/Auth/Keys",
                headers=self._headers(),
                params={"app": app_name},
                timeout=5.0,
            )
            if resp.status_code not in (200, 204):
                return ""
            listed = requests.get(f"{self.base_url}/Auth/Keys", headers=self._headers(), timeout=5.0)
            if listed.status_code != 200:
                return ""
            data = listed.json()
            rows = data.get("Items") if isinstance(data, dict) else data
            if not isinstance(rows, list):
                return ""
            for row in rows:
                if not isinstance(row, dict):
                    continue
                token = str(row.get("AccessToken") or row.get("Token") or "").strip()
                if token:
                    self.api_key = token
                    return token
        except Exception as exc:
            logger.debug("Jellyfin create_api_key error: %s", exc)
        return ""

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
