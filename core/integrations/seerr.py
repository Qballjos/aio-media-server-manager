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
from fastapi import HTTPException

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


# Host the Seerr links were last pointed at. ponytail: in memory, so one write per host per run.
_external_links_host: str | None = None


def sync_seerr_external_links(host: str) -> None:
    """Point Seerr's "Open in Radarr/Sonarr" and "Play on Jellyfin" links at the address the
    browser reaches AIO on. AIO links Seerr to the apps over 127.0.0.1, which only works
    inside the container. Only LAN access tells us that address, so other hosts are skipped.
    """
    global _external_links_host
    from applications.catalog import ApplicationCatalog
    from core.app_web_url import is_lan_hostname
    from core.integrations.credentials import get_application_api_key

    host = (host or "").strip().lower()
    if host in {"", "127.0.0.1", "localhost", "::1"} or not is_lan_hostname(host) or host == _external_links_host:
        return
    catalog = ApplicationCatalog()
    if not catalog.has("seerr") or not catalog.get("seerr").is_installed():
        return
    plugin = catalog.get("seerr")
    key = get_application_api_key("seerr", plugin.config_dir)
    if not key:
        return
    base = f"http://127.0.0.1:{plugin.port}/api/v1"
    headers = {"X-Api-Key": key}

    def ours(current: Any, want: str) -> bool:
        """Only fill an empty link or one on a LAN/loopback address; a public URL someone set
        (https://jellyfin.example.com for remote viewers) is theirs and stays."""
        current = str(current or "").strip()
        if current == want:
            return False
        link_host = current.split("://", 1)[-1].split("/", 1)[0].rsplit(":", 1)[0].strip("[]").lower()
        return not current or is_lan_hostname(link_host)

    try:
        for kind in ("radarr", "sonarr"):
            for server in requests.get(f"{base}/settings/{kind}", headers=headers, timeout=10).json():
                want = f"http://{host}:{server.get('port')}"
                if not ours(server.get("externalUrl"), want):
                    continue
                server_id = server.pop("id")
                server["externalUrl"] = want
                requests.put(f"{base}/settings/{kind}/{server_id}", headers=headers, json=server, timeout=15).raise_for_status()
        jellyfin = requests.get(f"{base}/settings/jellyfin", headers=headers, timeout=10).json()
        want = f"http://{host}:{jellyfin.get('port') or 8096}"
        if jellyfin.get("ip") and ours(jellyfin.get("externalHostname"), want):
            body = {k: jellyfin[k] for k in ("ip", "port", "useSsl", "urlBase", "jellyfinForgotPasswordUrl") if k in jellyfin}
            body["externalHostname"] = want
            requests.post(f"{base}/settings/jellyfin", headers=headers, json=body, timeout=15).raise_for_status()
    except (requests.RequestException, ValueError, TypeError, AttributeError) as exc:
        logger.debug("Seerr external links not updated yet: %s", exc)
        return
    _external_links_host = host
    logger.info("Seerr links to Radarr, Sonarr and Jellyfin now use %s.", host)


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

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.http.close()

    def _media_users_api(self, path: str, payload: dict | None = None, *, as_user: int | None = None) -> Any:
        headers = self._headers()
        if as_user is not None:
            headers["X-API-User"] = str(as_user)
        try:
            response = self.http.request(
                "GET" if payload is None else "POST", f"{self.base_url}{path}",
                headers=headers, json=payload, timeout=20, allow_redirects=False,
            )
            if as_user is not None and 400 <= response.status_code < 500:
                raise HTTPException(409, "This title could not be requested.")
            if response.status_code not in (200, 201):
                raise ValueError("Unexpected Seerr response status")
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            raise HTTPException(502, "Seerr could not complete the media user operation.") from exc

    def media_user_source(self) -> tuple[str, str]:
        kind = self._media_users_api("/settings/main").get("mediaServerType")
        if kind not in (1, MEDIA_SERVER_JELLYFIN):
            raise HTTPException(409, "Connect Jellyfin or Plex in Seerr first.")
        provider, key = ("plex", "machineId") if kind == 1 else ("jellyfin", "serverID")
        source = self._media_users_api(f"/settings/{provider}")
        server_id = source.get(key) if provider == "plex" else source.get("serverId") or source.get(key)
        if not isinstance(server_id, str) or not server_id:
            raise HTTPException(409, "Seerr did not identify its media server.")
        return provider, server_id

    def _users(self):
        skip = 0
        while True:
            page = self._media_users_api(f"/user?take=50&skip={skip}")
            rows = page["results"]
            yield from rows
            skip += len(rows)
            if not rows or skip >= page["pageInfo"]["results"]:
                return

    @staticmethod
    def _provider_user(provider: str, row: dict) -> str:
        id_key, user_type = ("plexId", 1) if provider == "plex" else ("jellyfinUserId", 3)
        account_id = row.get(id_key)
        if row.get("userType") == user_type and account_id and row.get("id") != 1:
            return str(account_id)
        return ""

    def media_user_accounts(self, provider: str) -> tuple[dict[str, str], dict[str, str]]:
        candidates = {}
        for row in self._media_users_api(f"/settings/{provider}/users"):
            if row.get("id") is not None:
                candidates[str(row["id"])] = row.get("username") or row.get("title") or str(row["id"])
        imported = {}
        for row in self._users():
            account_id = self._provider_user(provider, row)
            if account_id:
                imported[account_id] = (
                    row.get("displayName") or row.get("username") or row.get("plexUsername") or account_id
                )
            elif row.get("id") == 1:
                candidates.pop(str(row.get("plexId" if provider == "plex" else "jellyfinUserId")), None)
        return candidates, imported

    def member_user_id(self, provider: str, server_id: str, account_id: str) -> int:
        if self.media_user_source() == (provider, server_id):
            for row in self._users():
                user_id = row.get("id")
                if self._provider_user(provider, row) == account_id and type(user_id) is int and user_id > 1:
                    return user_id
        raise HTTPException(403, "The media account is no longer linked to Seerr.")

    def user_requests(self, user_id: int, take: int, skip: int) -> dict:
        return self._media_users_api(f"/user/{user_id}/requests?take={take}&skip={skip}")

    def review_request(self, request_id: int, action: str) -> None:
        result = self._media_users_api(f"/request/{request_id}/{action}", {})
        expected = 2 if action == "approve" else 3
        if not isinstance(result, dict) or result.get("id") != request_id or result.get("status") != expected:
            raise HTTPException(502, "Seerr did not confirm the decision.")

    def trending_request_coverage(self, titles: set[tuple[str, int]]) -> dict[tuple[str, int], set[int]]:
        """Match pending and approved requests without returning request identities."""
        covered: dict[tuple[str, int], set[int]] = {}
        skip = 0
        while True:
            payload = self._media_users_api(f"/request?take=100&skip={skip}&filter=all")
            rows = payload["results"]
            for row in rows:
                if row.get("status") not in (1, 2):
                    continue
                media = row.get("media") or {}
                key = (row.get("type") or media.get("mediaType"), media.get("tmdbId"))
                if key not in titles:
                    continue
                seasons = covered.setdefault(key, set())
                seasons.update(
                    season["seasonNumber"] for season in (row.get("seasons") or [])
                    if isinstance(season, dict) and type(season.get("seasonNumber")) is int and season["seasonNumber"] >= 0
                )
            skip += len(rows)
            if not rows or skip >= payload["pageInfo"]["results"]:
                return covered

    def request_seasons(self, media_id: int) -> list[int]:
        return sorted(self.request_season_counts(media_id))

    def request_season_counts(self, media_id: int) -> dict[int, int | None]:
        details = self._media_users_api(f"/tv/{media_id}")
        return {
            season["seasonNumber"]: season.get("episodeCount")
            for season in details.get("seasons", [])
            if isinstance(season, dict) and type(season.get("seasonNumber")) is int and season["seasonNumber"] >= 0
        }

    def submit_member_request(self, user_id: int, payload: dict) -> int:
        actor = self._media_users_api("/auth/me", as_user=user_id)
        if not isinstance(actor, dict) or actor.get("id") != user_id:
            raise HTTPException(502, "Seerr could not verify the request account.")
        request = self._media_users_api("/request", payload, as_user=user_id)
        owner = request.get("requestedBy") if isinstance(request, dict) else None
        request_id = request.get("id") if isinstance(request, dict) else None
        if not isinstance(owner, dict) or owner.get("id") != user_id or type(request_id) is not int:
            raise HTTPException(502, "Seerr could not confirm the request.")
        return request_id

    def user_quota(self, user_id: int) -> dict:
        return self._media_users_api(f"/user/{user_id}/quota")

    def import_media_users(self, provider: str, account_ids: list[str]) -> None:
        key = "plexIds" if provider == "plex" else "jellyfinUserIds"
        self._media_users_api(f"/user/import-from-{provider}", {key: account_ids})

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
