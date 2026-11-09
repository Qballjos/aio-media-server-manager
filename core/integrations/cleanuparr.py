"""Cleanuparr v2 HTTP integration with one-time, conservative setup defaults."""
from __future__ import annotations

import json
import threading
from urllib.parse import quote

import requests

from core.crypto import secret_store

_setup_lock = threading.RLock()
_ADMIN = "cleanuparr_managed_admin"
_INITIALIZED = "cleanuparr_safe_defaults"
_TYPES = {"qbittorrent": "qBittorrent", "sabnzbd": "Sabnzbd"}


class CleanuparrError(RuntimeError):
    pass


class CleanuparrClient:
    def __init__(self, port: int = 11011, api_key: str | None = None, http=None):
        self.base_url = f"http://127.0.0.1:{int(port)}/api"
        self.http = http or requests.Session()
        self.api_key = api_key or secret_store.get_secret("cleanuparr_api_key")

    def request(self, method: str, path: str, data=None, *, allow_conflict=False):
        headers = {"X-Api-Key": self.api_key} if self.api_key else {}
        try:
            response = self.http.request(method, f"{self.base_url}/{path}", json=data,
                                         headers=headers, timeout=(3, 15), allow_redirects=False)
            if allow_conflict and response.status_code == 409:
                return None
            response.raise_for_status()
            return response.json() if response.content else {}
        except (requests.RequestException, ValueError):
            # Error bodies can echo credentials; expose only the operation.
            raise CleanuparrError(f"Cleanuparr could not {method} {path}. Check its status and login.") from None

    def login(self, username: str, password: str) -> dict:
        result = self.request("POST", "auth/login", {"username": username, "password": password})
        tokens = result.get("tokens") or {}
        if result.get("requiresTwoFactor") or not tokens.get("accessToken"):
            raise CleanuparrError("Cleanuparr requires its own sign-in or two-factor authentication.")
        return tokens

    def ensure_admin(self, username: str, password: str) -> None:
        with _setup_lock:
            previous = json.loads(secret_store.get_secret(_ADMIN) or "null")
            status = self.request("GET", "auth/status")
            fresh = not status.get("setupCompleted")
            if fresh:
                self.api_key = None
                created = self.request("POST", "auth/setup/account",
                                       {"username": username, "password": password}, allow_conflict=True)
                if created is None and previous != {"username": username, "password": password}:
                    raise CleanuparrError("Cleanuparr already has an unfinished account. Complete its setup first.")
                if created is not None:
                    secret_store.delete_secret(_INITIALIZED)
                secret_store.save_secret(_ADMIN, json.dumps({"username": username, "password": password}))
                self.request("POST", "auth/setup/complete", {})
            elif self.api_key and previous:
                account = self.request("GET", "account")
                if account.get("username") != previous["username"]:
                    raise CleanuparrError("Cleanuparr's administrator changed. Check its account before syncing the AIO login.")
                if previous["username"] != username:
                    self.request("PUT", "account/username", {"newUsername": username, "currentPassword": previous["password"]})
                    previous["username"] = username
                    secret_store.save_secret(_ADMIN, json.dumps(previous))
                if previous["password"] != password:
                    self.request("PUT", "account/password", {"currentPassword": previous["password"], "newPassword": password})
                    previous["password"] = password
                    secret_store.save_secret(_ADMIN, json.dumps(previous))

            if not self.api_key or fresh:
                tokens = self.login(username, password)
                self.http.headers["Authorization"] = f"Bearer {tokens['accessToken']}"
                key = self.request("GET", "account/api-key").get("apiKey")
                if not key:
                    raise CleanuparrError("Cleanuparr did not return an API key.")
                self.api_key = key
                secret_store.save_secret("cleanuparr_api_key", key)
            # Only accounts AIO created receive safe defaults. Retry before wiring if it failed.
            if secret_store.get_secret(_ADMIN) and not secret_store.get_secret(_INITIALIZED):
                self._seed_defaults()
                secret_store.save_secret(_INITIALIZED, "true")

    def _save_defaults(self, section: str, changes: dict) -> None:
        path = f"configuration/{section}"
        current = self.request("GET", path)
        self.request("PUT", path, {**current, **changes})
        saved = self.request("GET", path)
        if any(saved.get(key) != value for key, value in changes.items()):
            raise CleanuparrError(f"Cleanuparr did not save its {section} defaults. Retry setup.")

    def _seed_defaults(self) -> None:
        # Confirm dry-run before enabling any scheduled job or adding connections.
        self._save_defaults("general", {
            "dryRun": True, "connectivityCheckEnabled": True,
            "connectivityCheckUrls": ["https://github.com", "https://www.cloudflare.com"],
            "httpCertificateValidation": "Enabled",
        })
        rules = self.request("GET", "queue-rules/stall")
        if not rules:
            self.request("POST", "queue-rules/stall", {
                "name": "AIO public stalled downloads", "enabled": True, "maxStrikes": 12,
                "privacyType": "Public", "minCompletionPercentage": 0, "maxCompletionPercentage": 100,
                "resetStrikesOnProgress": True, "deletePrivateTorrentsFromClient": False,
                "changeCategory": False,
            })
            rules = self.request("GET", "queue-rules/stall")
            if not any(r.get("name") == "AIO public stalled downloads" and r.get("maxStrikes") == 12
                       and r.get("privacyType") == "Public" for r in rules):
                raise CleanuparrError("Cleanuparr did not save its public stall rule. Retry setup.")
        self._save_defaults("queue_cleaner", {
            "enabled": True, "cronExpression": "0 0/5 * * * ?", "useAdvancedScheduling": False,
            "processNoContentId": False, "downloadingMetadataMaxStrikes": 0,
            "errored": {"maxStrikes": 0, "ignorePrivate": True, "deletePrivate": False, "changeCategory": False},
            "failedImport": {
                "maxStrikes": 6, "ignorePrivate": True, "deletePrivate": False,
                "skipIfNotFoundInClient": True, "patternMode": "Include",
                "patterns": ["title mismatch", "not found in the grabbed release", "was unexpected considering",
                             "No files found are eligible for import", "not imported or missing", "Unable to parse"],
                "changeCategory": False, "forceImport": False, "forceImportMaxTries": 3,
            },
        })
        blocklist = {"enabled": True, "blocklistType": "Blacklist",
                     "blocklistPath": "https://cleanuparr.pages.dev/static/blacklist_permissive"}
        self._save_defaults("malware_blocker", {
            "enabled": True, "cronExpression": "0 * * * * ?", "useAdvancedScheduling": False,
            "ignorePrivate": True, "deletePrivate": False, "processNoContentId": False,
            "deleteIfAnyFileBlocked": False, "sonarr": blocklist, "radarr": blocklist,
        })
        # Seeding/orphan deletion and proactive searching need operator-specific choices.
        self._save_defaults("download_cleaner", {"enabled": False})
        self._save_defaults("seeker", {"searchEnabled": True, "proactiveSearchEnabled": False, "searchInterval": 10})

    def ensure_arr(self, name: str, *, url: str, api_key: str, version: int) -> bool:
        path = f"configuration/{name}"
        rows = self.request("GET", path)["instances"]
        label = f"AIO {name.title()}"
        existing = next((r for r in rows if r.get("name") == label), None)
        data = {**(existing or {}), "name": label, "url": url, "apiKey": api_key, "version": version}
        data.setdefault("enabled", True)
        target = f"{path}/instances"
        if existing:
            target += f"/{quote(str(existing['id']), safe='')}"
        self.request("PUT" if existing else "POST", target, data)
        return any(r.get("name") == label and r.get("url", "").rstrip("/") == url.rstrip("/")
                   and r.get("enabled") == data["enabled"] for r in self.request("GET", path)["instances"])

    def ensure_download_client(self, name: str, *, host: str, **credentials) -> bool:
        path = "configuration/download_client"
        rows = self.request("GET", path)["clients"]
        label = f"AIO {_TYPES[name]}"
        existing = next((r for r in rows if r.get("name") == label), None)
        data = {**(existing or {}), "name": label, "typeName": _TYPES[name], "host": host, **credentials}
        data.setdefault("enabled", True)
        target = f"{path}/{quote(str(existing['id']), safe='')}" if existing else path
        self.request("PUT" if existing else "POST", target, data)
        return any(r.get("name") == label and r.get("host", "").rstrip("/") == host.rstrip("/")
                   and r.get("enabled") == data["enabled"] for r in self.request("GET", path)["clients"])


def wire_cleanuparr(catalog) -> list[dict]:
    from core.integrations.credentials import get_application_api_key
    from core.integrations.qbittorrent import qbittorrent_credentials
    from core.shared_credentials import shared_admin_credentials

    plugin = catalog.get("cleanuparr")
    api = CleanuparrClient(port=plugin.port)
    creds = shared_admin_credentials()
    if not creds:
        raise CleanuparrError("Save the AIO administrator login before connecting Cleanuparr.")
    api.ensure_admin(*creds)
    steps = []
    for name, version in (("sonarr", 4), ("radarr", 6), ("lidarr", 3)):
        app = catalog.get(name)
        if not app.is_installed():
            continue
        key = get_application_api_key(name, app.config_dir)
        if not key:
            raise CleanuparrError(f"Cleanuparr needs the {name} API key. Start {name}, then retry Auto-Wire.")
        ok = api.ensure_arr(name, url=f"http://127.0.0.1:{app.port}", api_key=key, version=version)
        steps.append({"target": "cleanuparr", "action": f"connect_{name}",
                      "status": "success" if ok else "warning", "detail": f"AIO {name} connection read back" if ok else "Connection did not match"})
    for name in ("qbittorrent", "sabnzbd"):
        app = catalog.get(name)
        if not app.is_installed():
            continue
        if name == "qbittorrent":
            user, password = qbittorrent_credentials()
            credentials = {"username": user, "password": password}
        else:
            key = get_application_api_key(name, app.config_dir)
            if not key:
                raise CleanuparrError("Cleanuparr needs the SABnzbd API key. Start SABnzbd, then retry Auto-Wire.")
            credentials = {"apiKey": key}
        ok = api.ensure_download_client(name, host=f"http://127.0.0.1:{app.port}", **credentials)
        steps.append({"target": "cleanuparr", "action": f"connect_{name}",
                      "status": "success" if ok else "warning", "detail": f"AIO {name} connection read back" if ok else "Connection did not match"})
    if not all(step["status"] == "success" for step in steps):
        raise CleanuparrError("Cleanuparr connections did not match after saving. Retry Auto-Wire.")
    return steps


def verify_cleanuparr(catalog, *, api=None) -> list[tuple[str, bool]]:
    """Read-only checks: disabled connections are reported, never re-enabled."""
    api = api or CleanuparrClient(port=catalog.get("cleanuparr").port)
    checks = []
    for name in ("sonarr", "radarr", "lidarr"):
        app = catalog.get(name)
        if app.is_installed():
            rows = api.request("GET", f"configuration/{name}")["instances"]
            expected = f"http://127.0.0.1:{app.port}"
            checks.append((f"Connection: {name}", any(
                r.get("enabled") is True and r.get("name") == f"AIO {name.title()}"
                and r.get("url", "").rstrip("/") == expected for r in rows)))
    clients = None
    for name in ("qbittorrent", "sabnzbd"):
        app = catalog.get(name)
        if app.is_installed():
            if clients is None:
                clients = api.request("GET", "configuration/download_client")["clients"]
            expected = f"http://127.0.0.1:{app.port}"
            checks.append((f"Connection: {name}", any(
                r.get("enabled") is True and r.get("name") == f"AIO {_TYPES[name]}"
                and r.get("host", "").rstrip("/") == expected for r in clients)))
    return checks
