"""Read actual application configuration, never mutate it or return credentials."""
from urllib.parse import urlparse
import time
import requests

from applications.catalog import ApplicationCatalog
from core.integrations.credentials import get_application_api_key
from core.library_layout import LibraryLayout, arr_root_folders
from core.settings import settings


def verify_integrations(cfg=None, catalog=None):
    cfg = cfg or settings
    catalog = catalog or ApplicationCatalog(app_settings=cfg)
    checks = []
    installed = {p.name: p for p in catalog.all_plugins() if p.is_installed()}
    def add(app, name, ok, detail):
        checks.append({"app": app, "name": name, "status": "pass" if ok else "failed", "detail": detail,
                       "hint": "" if ok else "Start the affected apps, then run Auto-Wire and check again. Custom connections can be corrected in the app."})
    def read(plugin, path, version="v3"):
        key = get_application_api_key(plugin.name, plugin.config_dir)
        if not key:
            raise ValueError("missing key")
        response = requests.get(f"http://127.0.0.1:{plugin.port}/api/{version}{path}", headers={"X-Api-Key": key}, timeout=(2, 5))
        response.raise_for_status()
        return response.json()
    def fields(row):
        return {str(f.get("name", "")).lower(): f.get("value") for f in row.get("fields", []) if isinstance(f, dict)}
    def matches_port(value, port):
        try:
            url = urlparse(str(value))
            return url.hostname in {"localhost", "127.0.0.1", "::1"} and url.port == port
        except ValueError:
            return False
    roots = arr_root_folders(LibraryLayout.from_settings(cfg))
    for name in ("sonarr", "radarr", "lidarr"):
        if name not in installed:
            continue
        plugin = installed[name]
        version = "v1" if name == "lidarr" else "v3"
        try:
            configured = read(plugin, "/rootfolder", version)
            actual = {str(r.get("path", "")).rstrip("/") for r in configured}
            ok = all(str(p).rstrip("/") in actual for p in roots[name])
            add(name, "Library folders", ok, "Expected media folders are configured" if ok else "One or more expected library folders are missing")
            clients = read(plugin, "/downloadclient", version)
            for downloader, implementation in (("qbittorrent", "QBittorrent"), ("sabnzbd", "Sabnzbd"), ("nzbget", "Nzbget")):
                if downloader not in installed:
                    continue
                def wired(row):
                    f = fields(row)
                    category = f.get({"sonarr": "tvcategory", "radarr": "moviecategory", "lidarr": "musiccategory"}[name], f.get("category"))
                    return row.get("enable") is True and row.get("implementation") == implementation and str(f.get("port")) == str(installed[downloader].port) and f.get("host") in {"127.0.0.1", "localhost"} and category == name
                ok = any(wired(row) for row in clients)
                add(name, f"Download client: {downloader}", ok, "Client, address, port and category match" if ok else "Download client is missing, disabled or configured differently")
        except (requests.RequestException, ValueError, TypeError, KeyError):
            add(name, "Read configuration", False, "App configuration could not be read; check its status and API key")
    if "prowlarr" in installed:
        try:
            apps = read(installed["prowlarr"], "/applications", "v1")
            for name in ("sonarr", "radarr", "lidarr"):
                if name in installed:
                    ok = any(str(row.get("implementation", "")).lower() == name and row.get("syncLevel") not in {"disabled", None} and matches_port(fields(row).get("baseurl"), installed[name].port) for row in apps)
                    add("prowlarr", f"Indexer sync: {name}", ok, "Application synchronization matches" if ok else "Application synchronization is missing or differs")
            indexers = read(installed["prowlarr"], "/indexer", "v1")
            add("prowlarr", "Search sources", any(row.get("enable") for row in indexers), "At least one enabled indexer is needed for searches; choose sources in Prowlarr")
        except (requests.RequestException, ValueError, TypeError):
            add("prowlarr", "Read configuration", False, "Prowlarr could not be read; check status and API key")
    if "seerr" in installed:
        try:
            for name in ("sonarr", "radarr"):
                if name not in installed:
                    continue
                rows = read(installed["seerr"], f"/settings/{name}", "v1")
                ok = any(str(row.get("port")) == str(installed[name].port) and row.get("hostname") in {"localhost", "127.0.0.1"} and row.get("apiKey") and row.get("isDefault") for row in rows)
                add("seerr", f"Requests: {name}", bool(ok), "Default request target is configured" if ok else "Default request target is missing or differs")
        except (requests.RequestException, ValueError, TypeError):
            add("seerr", "Read configuration", False, "Seerr could not be read; complete its sign-in and check its API key")
    if "cleanuparr" in installed:
        from core.integrations.cleanuparr import CleanuparrError, verify_cleanuparr
        try:
            results = verify_cleanuparr(catalog)
            for name, ok in results:
                add("cleanuparr", name, ok, "Connection matches" if ok else "Connection is missing, disabled or configured differently")
            if not results:
                add("cleanuparr", "Connected applications", False, "Install a supported Arr application or download client, then run Auto-Wire")
        except (CleanuparrError, ValueError, TypeError, KeyError):
            add("cleanuparr", "Read configuration", False, "Cleanuparr could not be read; check its status and saved API key")
    return {"checked_at": time.time(), "ok": bool(checks) and all(c["status"] == "pass" for c in checks), "checks": checks}
