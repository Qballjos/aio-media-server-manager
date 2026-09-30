"""Jellyfin REST helpers for libraries and transcoding temp path."""

from __future__ import annotations

import logging
import re
import sqlite3
import time
from typing import Any, Optional
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

_AUTH_HEADER = (
    'MediaBrowser Client="AIO Media Server Manager", Device="AMM", DeviceId="amm-jellyfin", Version="1.0.0", Token=""'
)
_PLACEHOLDER_USERS = ("jellyfin", "root", "MyJellyfinUser")
_STARTUP_CONFIG = {
    "UICulture": "en-US",
    "MetadataCountryCode": "US",
    "PreferredMetadataLanguage": "en",
}


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


def jellyfin_root(config_dir: Path) -> Path:
    """Accept either the Jellyfin root or the plugin config subdirectory."""
    path = Path(config_dir)
    if path.name == "config" and (path / "system.xml").is_file():
        return path.parent
    if (path / "config" / "system.xml").is_file():
        return path
    if path.name == "config":
        return path.parent
    return path


def mark_jellyfin_wizard_incomplete(config_dir: Path) -> bool:
    """Allow the startup API to run again when Complete ran with no local user."""
    xml = jellyfin_root(config_dir) / "config" / "system.xml"
    if not xml.is_file():
        return False
    try:
        text = xml.read_text(encoding="utf-8")
    except OSError:
        return False
    if "<IsStartupWizardCompleted>false</IsStartupWizardCompleted>" in text:
        return True
    updated = text.replace(
        "<IsStartupWizardCompleted>true</IsStartupWizardCompleted>",
        "<IsStartupWizardCompleted>false</IsStartupWizardCompleted>",
    )
    if updated == text:
        return False
    try:
        xml.write_text(updated, encoding="utf-8")
    except OSError:
        return False
    return True


def jellyfin_db_path(config_dir: Path) -> Path:
    return jellyfin_root(config_dir) / "data" / "data" / "jellyfin.db"


def jellyfin_database_is_corrupt(config_dir: Path | None) -> bool:
    if not config_dir:
        return False
    db = jellyfin_db_path(config_dir)
    if not db.is_file():
        return False
    try:
        with sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True) as conn:
            row = conn.execute("PRAGMA integrity_check").fetchone()
        return not (row and str(row[0]).lower() == "ok")
    except sqlite3.Error:
        return True


def quarantine_corrupt_jellyfin_database(config_dir: Path) -> bool:
    """Move a malformed jellyfin.db aside so the server can recreate it."""
    parent = jellyfin_db_path(config_dir).parent
    if not parent.is_dir():
        return False
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest = parent / f"corrupt-{stamp}"
    dest.mkdir(parents=True, exist_ok=True)
    moved = False
    for name in ("jellyfin.db", "jellyfin.db-wal", "jellyfin.db-shm"):
        src = parent / name
        if src.exists():
            src.rename(dest / name)
            moved = True
    if moved:
        logger.warning("Quarantined corrupt Jellyfin database under %s", dest)
        mark_jellyfin_wizard_incomplete(config_dir)
    return moved


def jellyfin_user_count(config_dir: Path | None) -> int | None:
    if not config_dir:
        return None
    db = jellyfin_db_path(config_dir)
    if not db.is_file():
        return None
    if jellyfin_database_is_corrupt(config_dir):
        return None
    try:
        with sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True) as conn:
            row = conn.execute("SELECT COUNT(*) FROM Users").fetchone()
        return int(row[0] if row else 0)
    except sqlite3.Error:
        return None


def discover_jellyfin_api_key(config_dir: Path | None = None, port: int = 8096) -> str:
    """Finish startup if needed, then log in with the shared manager account."""
    from core.shared_credentials import shared_admin_credentials

    creds = shared_admin_credentials()
    if not creds:
        return ""
    username, password = creds
    if not username or not password:
        return ""
    client = JellyfinClient(
        port=_jellyfin_listen_port(config_dir, port),
        config_dir=config_dir,
    )
    if not client.ensure_local_admin(username, password):
        return ""
    token = client.authenticate(username, password) or client.api_key or ""
    if not token:
        return ""
    return client.create_api_key("AIO-Media-Manager") or token


class JellyfinClient:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8096,
        api_key: Optional[str] = None,
        config_dir: Path | None = None,
    ) -> None:
        self.base_url = f"http://{host}:{port}"
        self.api_key = api_key
        self.config_dir = Path(config_dir) if config_dir else None
        self._user_id = ""
        self._user_name = ""
        self._auth_password = ""

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
                    timeout=8.0,
                )
                if resp.status_code != 200:
                    logger.debug("Jellyfin authenticate failed (%s): %s", resp.status_code, resp.text[:300])
                    continue
                data = resp.json()
                token = str((data or {}).get("AccessToken") or "").strip()
                if token:
                    self.api_key = token
                    self._auth_password = password
                    user = (data or {}).get("User") if isinstance(data, dict) else None
                    if isinstance(user, dict):
                        self._user_id = str(user.get("Id") or "")
                        self._user_name = str(user.get("Name") or username)
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
        """Finish Jellyfin's first-run wizard and set the manager admin login."""
        if self._wizard_completed():
            return True
        placeholder = self._wait_first_user()
        if placeholder is None:
            logger.warning("Jellyfin startup wizard API was not ready.")
            return False
        self._post_json("/Startup/Configuration", {**_STARTUP_CONFIG, "ServerName": "Jellyfin"})
        created = self._post_json("/Startup/User", {"Name": username, "Password": password})
        if created is None or created.status_code not in (200, 204, 403):
            status = created.status_code if created is not None else "no-response"
            body = created.text[:300] if created is not None else ""
            logger.warning("Jellyfin POST /Startup/User failed (%s): %s", status, body)
            if placeholder and placeholder.lower() != username.lower():
                created = self._post_json(
                    "/Startup/User",
                    {"Name": placeholder, "Password": password},
                )
        user_ok = created is not None and created.status_code in (200, 204)
        already_set = created is not None and created.status_code == 403
        if not user_ok and not already_set:
            logger.warning("Refusing to complete Jellyfin setup: first user was not created.")
            return False
        self._post_json(
            "/Startup/RemoteAccess",
            {"EnableRemoteAccess": True, "EnableAutomaticPortMapping": False},
        )
        done = self._post_json("/Startup/Complete", None)
        if done is None or done.status_code not in (200, 204):
            logger.warning(
                "Jellyfin POST /Startup/Complete failed (%s)",
                done.status_code if done is not None else "no-response",
            )
            return False
        time.sleep(0.3)
        return True

    def _wizard_completed(self) -> bool:
        try:
            info = requests.get(f"{self.base_url}/System/Info/Public", timeout=4.0)
            if info.status_code == 200:
                payload = info.json() if info.content else {}
                if isinstance(payload, dict):
                    return bool(payload.get("StartupWizardCompleted"))
        except Exception as exc:
            logger.debug("Jellyfin public info error: %s", exc)
        return False

    def _wait_first_user(self, timeout: float = 20.0) -> str | None:
        """GET /Startup/User runs InitializeAsync and must succeed before POST User."""
        deadline = time.monotonic() + timeout
        while time.monotonic() <= deadline:
            try:
                cfg = requests.get(f"{self.base_url}/Startup/Configuration", timeout=4.0)
                user = requests.get(f"{self.base_url}/Startup/User", timeout=8.0)
                if cfg.status_code == 200 and user.status_code == 200:
                    payload = user.json() if user.content else {}
                    if isinstance(payload, dict):
                        return str(payload.get("Name") or "").strip()
                    return ""
            except Exception:
                pass
            time.sleep(0.5)
        return None

    def _post_json(self, path: str, payload: dict[str, Any] | None) -> requests.Response | None:
        try:
            kwargs: dict[str, Any] = {"timeout": 8.0}
            if payload is not None:
                kwargs["json"] = payload
            return requests.post(f"{self.base_url}{path}", **kwargs)
        except Exception as exc:
            logger.debug("Jellyfin POST %s error: %s", path, exc)
            return None

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
        self.complete_startup(username, password)
        if self.authenticate(username, password):
            return True

        candidates: list[str] = []
        for name in (*self.public_usernames(), *_PLACEHOLDER_USERS, self._user_name):
            label = (name or "").strip()
            if label and label.lower() not in {item.lower() for item in candidates}:
                candidates.append(label)

        for name in candidates:
            if self.authenticate(name, password) or self.authenticate(name, ""):
                if self._align_logged_in_user(username, password):
                    return bool(self.authenticate(username, password))

        if self.api_key and self._align_logged_in_user(username, password):
            return bool(self.authenticate(username, password))

        if self._recover_missing_first_user(username, password):
            return bool(self.authenticate(username, password))

        logger.warning("Jellyfin login '%s' could not be created or updated.", username)
        return False

    def _recover_missing_first_user(self, username: str, password: str) -> bool:
        """Complete ran with an empty Users table; reopen the wizard and create the admin."""
        if not self.config_dir:
            logger.warning("Jellyfin has no local users; config dir is unknown.")
            return False
        corrupt = jellyfin_database_is_corrupt(self.config_dir)
        count = jellyfin_user_count(self.config_dir)
        if not corrupt:
            if count is None:
                if self.public_usernames():
                    return False
            elif count > 0:
                return False
        if corrupt:
            logger.warning("Jellyfin database is malformed; quarantining it and reopening the wizard.")
            if not quarantine_corrupt_jellyfin_database(self.config_dir):
                logger.warning("Could not quarantine the corrupt Jellyfin database.")
                return False
        elif not mark_jellyfin_wizard_incomplete(self.config_dir):
            logger.warning("Jellyfin has no local users; could not reopen the startup wizard.")
            return False
        if not self._restart_jellyfin():
            logger.warning(
                "Reopened the Jellyfin startup wizard; restart Jellyfin to apply the manager login."
            )
            return False
        if not self._wait_wizard_open():
            logger.warning("Jellyfin did not return to the startup wizard after restart.")
            return False
        return self.complete_startup(username, password)

    def _wait_wizard_open(self, timeout: float = 45.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() <= deadline:
            if not self._wizard_completed():
                return True
            time.sleep(0.5)
        return False

    def _restart_jellyfin(self) -> bool:
        try:
            from core.supervisor import ProcessSupervisor

            supervisor = ProcessSupervisor.get()
            supervisor.run_coroutine_sync(supervisor.restart("jellyfin"), timeout=90.0)
            return True
        except Exception as exc:
            logger.warning("Could not restart Jellyfin: %s", exc)
            return False

    def _align_logged_in_user(self, username: str, password: str) -> bool:
        user_id = self._user_id or self._first_user_id()
        if not user_id:
            created = self._post_auth_json("/Users/New", {"Name": username, "Password": password})
            return created is not None and created.status_code in (200, 204)
        current = (self._user_name or "").strip()
        if current.lower() != username.lower() and not self._rename_user(user_id, username):
            created = self._post_auth_json("/Users/New", {"Name": username, "Password": password})
            return created is not None and created.status_code in (200, 204)
        return self._set_password(user_id, password)

    def _first_user_id(self) -> str:
        try:
            resp = requests.get(f"{self.base_url}/Users", headers=self._headers(), timeout=5.0)
            if resp.status_code != 200:
                return ""
            users = resp.json()
            if not isinstance(users, list):
                return ""
            for user in users:
                if not isinstance(user, dict) or not user.get("Id"):
                    continue
                policy = user.get("Policy") if isinstance(user.get("Policy"), dict) else {}
                if policy.get("IsAdministrator") is False:
                    continue
                return str(user["Id"])
            for user in users:
                if isinstance(user, dict) and user.get("Id"):
                    return str(user["Id"])
        except Exception as exc:
            logger.debug("Jellyfin list users error: %s", exc)
        return ""

    def _rename_user(self, user_id: str, username: str) -> bool:
        try:
            current = requests.get(
                f"{self.base_url}/Users/{user_id}",
                headers=self._headers(),
                timeout=5.0,
            )
            payload: dict[str, Any] = current.json() if current.status_code == 200 and current.content else {}
            if not isinstance(payload, dict):
                payload = {}
            payload["Name"] = username
            resp = requests.post(
                f"{self.base_url}/Users/{user_id}",
                headers=self._headers(),
                json=payload,
                timeout=8.0,
            )
            if resp.status_code in (200, 204):
                self._user_name = username
                return True
        except Exception as exc:
            logger.debug("Jellyfin rename user error: %s", exc)
        return False

    def _set_password(self, user_id: str, password: str) -> bool:
        known = self._auth_password or ""
        bodies = (
            {"CurrentPw": known, "NewPw": password, "ResetPassword": False},
            {"CurrentPw": "", "NewPw": password, "ResetPassword": False},
            {"CurrentPassword": known, "NewPw": password},
            {"ResetPassword": True, "NewPw": password},
            {"NewPw": password},
        )
        for body in bodies:
            resp = self._post_auth_json(f"/Users/{user_id}/Password", body)
            if resp is not None and resp.status_code in (200, 204):
                if body.get("ResetPassword") and password:
                    follow = self._post_auth_json(
                        f"/Users/{user_id}/Password",
                        {"CurrentPw": "", "NewPw": password, "ResetPassword": False},
                    )
                    return follow is not None and follow.status_code in (200, 204)
                return True
        return False

    def _post_auth_json(self, path: str, payload: dict[str, Any]) -> requests.Response | None:
        try:
            return requests.post(
                f"{self.base_url}{path}",
                headers=self._headers(),
                json=payload,
                timeout=8.0,
            )
        except Exception as exc:
            logger.debug("Jellyfin POST %s error: %s", path, exc)
            return None
