"""
core/integrations/seerr.py — Seerr REST API client.

Seerr creates its first admin only through a media-server sign-in (Jellyfin,
Emby, or Plex); /settings/initialize needs that admin's session, and the
X-Api-Key header only resolves to a user once user #1 exists. So every setup
call here runs on a signed-in requests.Session, with the API key as a fallback
for read-only calls on an already-initialized Seerr.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

import requests

from core.shared_credentials import admin_email, shared_admin_credentials

logger = logging.getLogger(__name__)

MEDIA_SERVER_JELLYFIN = 2  # Seerr MediaServerType enum value
SEERR_SESSION_MAX_AGE = 60 * 60 * 24 * 30  # matches Seerr's own cookie lifetime


def read_seerr_api_key(config_dir: Path | None) -> str:
    """Read Seerr apiKey from settings.json (written on first start)."""
    if not config_dir:
        return ""
    root = Path(config_dir)
    candidates = [root / "settings.json", root / "settings" / "main.json"]
    if root.is_dir():
        candidates.extend(sorted(root.glob("**/settings.json"))[:8])
    seen: set[Path] = set()
    for path in candidates:
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        key = _find_api_key(data)
        if key:
            return key
    return ""


def _find_api_key(obj: Any) -> str:
    if isinstance(obj, dict):
        for name in ("apiKey", "api_key"):
            value = str(obj.get(name) or "").strip()
            if len(value) >= 20:
                return value
        nested = obj.get("main")
        if isinstance(nested, dict):
            found = _find_api_key(nested)
            if found:
                return found
        for value in obj.values():
            found = _find_api_key(value)
            if found:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _find_api_key(item)
            if found:
                return found
    return ""


def seerr_admin_login(
    port: int,
    *,
    jellyfin_port: int | None = None,
    plex_token: str | None = None,
) -> Optional["SeerrClient"]:
    """Sign the shared manager admin in to Seerr; the returned client holds the session."""
    creds = shared_admin_credentials()
    if not creds:
        return None
    username, password = creds
    email = admin_email()
    if not email:
        try:
            from core.auth import auth_manager

            email = auth_manager.email()
        except Exception:
            email = ""
    client = SeerrClient(port=port)
    if client.login(
        username,
        password,
        email=email or f"{username}@localhost",
        jellyfin_port=jellyfin_port,
        plex_token=plex_token,
    ):
        return client
    return None


def discover_seerr_api_key(config_dir: Path | None = None, port: int = 5055) -> str:
    """Read apiKey from disk, else sign in and read it from Seerr's main settings."""
    disk = read_seerr_api_key(config_dir)
    if disk:
        return disk
    try:
        from core.app_prefs import load_app_ports

        port = int(load_app_ports().get("seerr") or port or 5055)
    except Exception:
        port = int(port or 5055)
    client = seerr_admin_login(port)
    return client.main_api_key() if client else ""


class SeerrClient:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 5055,
        api_key: Optional[str] = None,
        http: Optional[requests.Session] = None,
    ):
        self.base_url = f"http://{host}:{port}/api/v1"
        self.api_key = api_key
        self.http = http or requests.Session()
        self.logged_in = False
        self.media_server = ""  # "jellyfin" or "plex" after a successful login

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        # Seerr takes the API-key branch before the session when both are present,
        # and that branch fails until user #1 exists. Prefer the session.
        if self.api_key and not self.logged_in:
            headers["X-Api-Key"] = self.api_key
        return headers

    def _post(self, path: str, payload: Any, timeout: float = 8.0) -> requests.Response | None:
        try:
            return self.http.post(
                f"{self.base_url}{path}", headers=self._headers(), json=payload, timeout=timeout
            )
        except Exception as exc:
            logger.debug("Seerr POST %s error: %s", path, exc)
            return None

    def login(
        self,
        username: str,
        password: str,
        *,
        email: str = "",
        jellyfin_port: int | None = None,
        plex_token: str | None = None,
    ) -> bool:
        """Sign in the way Seerr accepts; on a fresh Seerr this also creates the admin.

        Order: plain Jellyfin sign-in (admin exists), Jellyfin first-run sign-in
        (creates the admin and configures the server), Plex token sign-in.
        """
        attempts: list[tuple[str, str, dict[str, Any]]] = [
            ("jellyfin", "/auth/jellyfin", {"username": username, "password": password})
        ]
        if jellyfin_port:
            attempts.append(
                (
                    "jellyfin",
                    "/auth/jellyfin",
                    {
                        "username": username,
                        "password": password,
                        "hostname": "127.0.0.1",
                        "port": int(jellyfin_port),
                        "useSsl": False,
                        "urlBase": "",
                        "email": email or f"{username}@localhost",
                        "serverType": MEDIA_SERVER_JELLYFIN,
                    },
                )
            )
        if plex_token:
            attempts.append(("plex", "/auth/plex", {"authToken": plex_token}))
        for kind, path, payload in attempts:
            resp = self._post(path, payload)
            if resp is not None and resp.status_code in (200, 201):
                self.logged_in = True
                self.media_server = kind
                logger.info("Signed in to Seerr via %s as '%s'.", kind, username)
                return True
        return False

    def main_api_key(self) -> str:
        try:
            resp = self.http.get(f"{self.base_url}/settings/main", headers=self._headers(), timeout=8.0)
        except Exception as exc:
            logger.debug("Seerr settings/main error: %s", exc)
            return ""
        return _find_api_key(resp.json()) if resp.status_code == 200 else ""

    def enable_all_libraries(self, kind: str) -> bool:
        """Sync libraries from the media server and enable each one for Seerr."""
        resp = self._post(f"/settings/{kind}/library/sync", None, timeout=30.0)
        if resp is None or resp.status_code != 200:
            return False
        ok = True
        for library in resp.json() or []:
            lib_id = library.get("id") if isinstance(library, dict) else None
            if lib_id is None:
                continue
            try:
                put = self.http.put(
                    f"{self.base_url}/settings/{kind}/library/{lib_id}",
                    headers=self._headers(),
                    json={"enabled": True},
                    timeout=8.0,
                )
                ok = put.status_code == 200 and ok
            except Exception as exc:
                logger.debug("Seerr enable library %s error: %s", lib_id, exc)
                ok = False
        return ok

    def initialize(self) -> bool:
        """Mark Seerr's first-run wizard as complete."""
        resp = self._post("/settings/initialize", None)
        return resp is not None and resp.status_code == 200

    def _connect_arr(self, kind: str, payload: dict[str, Any]) -> bool:
        try:
            existing = self.http.get(f"{self.base_url}/settings/{kind}", headers=self._headers(), timeout=5.0)
            if existing.status_code == 200 and len(existing.json()) > 0:
                logger.info("Seerr %s integration already configured.", kind.title())
                return True
            resp = self.http.post(
                f"{self.base_url}/settings/{kind}", headers=self._headers(), json=payload, timeout=5.0
            )
            return resp.status_code in (200, 201)
        except Exception as exc:
            logger.debug("Seerr connect_%s error: %s", kind, exc)
            return False

    def connect_radarr(
        self,
        host: str = "127.0.0.1",
        port: int = 7878,
        api_key: str = "",
        root_folder: str = "/data/media/movies",
    ) -> bool:
        """Link Radarr instance into Seerr."""
        return self._connect_arr(
            "radarr",
            {
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
                "minimumAvailability": "released",
                "isDefault": True,
            },
        )

    def connect_sonarr(
        self,
        host: str = "127.0.0.1",
        port: int = 8989,
        api_key: str = "",
        root_folder: str = "/data/media/tv",
    ) -> bool:
        """Link Sonarr instance into Seerr."""
        return self._connect_arr(
            "sonarr",
            {
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
                "enableSeasonFolders": True,
                "isDefault": True,
            },
        )

    def connect_jellyfin(
        self,
        host: str = "127.0.0.1",
        port: int = 8096,
        api_key: str = "",
    ) -> bool:
        """Link Jellyfin media server into Seerr (the Jellyfin sign-in normally does this)."""
        resp = self._post(
            "/settings/jellyfin",
            {"hostname": host, "port": port, "useSsl": False, "urlBase": "", "apiKey": api_key},
            timeout=5.0,
        )
        return resp is not None and resp.status_code in (200, 201)

    def connect_plex(
        self,
        host: str = "127.0.0.1",
        port: int = 32400,
    ) -> bool:
        """Link Plex Media Server into Seerr."""
        resp = self._post("/settings/plex", {"ip": host, "port": port, "useSsl": False}, timeout=5.0)
        return resp is not None and resp.status_code in (200, 201)
