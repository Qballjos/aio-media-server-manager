"""Isolated browser fixture: real manager routers; synthetic app/provider boundaries.

Never imported by main.py. Owns a TemporaryDirectory and starts no media processes.
"""
from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
from types import SimpleNamespace
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def build_app(root: Path):
    for name in ("config", "downloads", "media", "backups"):
        os.environ[f"AMM_{'DOWNLOAD' if name == 'downloads' else name.upper()}_DIR"] = str(root / name)
    os.environ["AMM_LOG_LEVEL"] = "ERROR"
    from fastapi import FastAPI, Request
    from fastapi.staticfiles import StaticFiles
    import requests
    import applications.catalog as catalog_mod
    from applications.base import BaseApplication
    from applications.manifest import InstallMethod
    from core.settings import settings
    from core.supervisor import ProcessState, ProcessSupervisor
    from core.library_layout import LibraryLayout, arr_root_folders
    from core.crypto import secret_store
    from core.auth import auth_manager
    from core.install_jobs import clear_jobs
    from core.backup_jobs import backup_jobs
    from core.updater import ApplicationUpdater
    from core.wizard import WizardEngine
    from api.routers import auth, wizard, catalog, applications, integrations, homepage, backups, notifications, settings as settings_router, updates

    state = {"wired": False, "source": False, "requested": False, "downloaded": False, "fail_update": False, "trending": False, "trending_detail_fail": False, "trending_statuses": False, "calendar_colors": False, "media_widgets": False, "service_status": False, "service_status_down": False}
    process_states = {}

    class Supervisor:
        def status(self, name):
            return ProcessState.RUNNING if process_states.get(name) else ProcessState.STOPPED
        async def start(self, name, **_kwargs): process_states[name] = True
        async def stop(self, name): process_states[name] = False
        async def restart(self, name): process_states[name] = True
        def list_processes(self):
            return [{"name": name, "state": "running" if running else "stopped", "pid": 123, "started_at": time.monotonic(), "is_crash_loop": False, "recent_crashes": 0} for name, running in process_states.items()]
        def get_logs(self, name): return [f"{name}: fixture ready"]
        def reset_crash_loop(self, name): pass
    supervisor = Supervisor()
    ProcessSupervisor.get = classmethod(lambda cls: supervisor)

    class FixtureApp(BaseApplication):
        def install(self):
            self.pre_install()
            if state["fail_update"] and self.name == "sonarr":
                (self.config_dir / "preferences.json").write_text('{"quality":"broken"}')
                raise RuntimeError("Synthetic update failure")
            (self.install_dir / self.executable_name).write_text("synthetic application")
            self.metadata_path().write_text(json.dumps({"version": "1.0.0"}))
            (self.config_dir / "preferences.json").write_text('{"quality":"original"}')
            secret_store.save_secret(f"{self.name}_api_key", f"fixture-{self.name}-key-1234567890")
            return SimpleNamespace(version="1.0.0")
        def build_start_command(self, executable): return [str(executable)]
    classes = tuple(type("Fixture" + cls.__name__, (FixtureApp,), {"manifest": replace(cls.manifest, github_repo="", install_method=InstallMethod.GITHUB_RELEASE)}) for cls in catalog_mod.PLUGIN_CLASSES)
    catalog_mod.PLUGIN_CLASSES = classes
    for current in list(catalog_mod._LIVE_CATALOGS):
        current._classes = classes
        current.reload()
    ApplicationUpdater._wait_healthy = lambda self, plugin: True

    async def finalize(plugin):
        await asyncio.sleep(0.04)
        await supervisor.start(plugin.name)
        state["wired"] = True
        return {"wired": True, "healthy": True}
    catalog.finalize_application_install = finalize
    async def wire(**_kwargs):
        state["wired"] = True
        return {"status": "complete", "steps": []}
    integrations.schedule_full_wiring = wire

    def response(data, status=200):
        result = requests.Response()
        result.status_code = status
        result._content = json.dumps(data).encode()
        result.headers["Content-Type"] = "application/json"
        return result
    def provider_get(url, **kwargs):
        parsed = urlsplit(url)
        if parsed.hostname == "api.github.com":
            return response({"resources": {"core": {"remaining": 50, "reset": 9999999999}}})
        if parsed.hostname != "127.0.0.1":
            raise RuntimeError("External network is disabled in the browser fixture")
        current = next((p for p in catalog.catalog.all_plugins() if p.port == parsed.port), None)
        if not current:
            return response({}, 404)
        path = parsed.path
        roots = arr_root_folders(LibraryLayout.from_settings(settings))
        if path.endswith("/rootfolder"):
            return response([{"path": str(p)} for p in roots.get(current.name, [])] if state["wired"] else [])
        if path.endswith("/downloadclient"):
            qbit = catalog.catalog.get("qbittorrent")
            return response([{"enable": True, "implementation": "QBittorrent", "fields": [{"name": "host", "value": "127.0.0.1"}, {"name": "port", "value": qbit.port}, {"name": "tvCategory", "value": current.name}, {"name": "movieCategory", "value": current.name}]}] if state["wired"] else [])
        if path.endswith("/applications"):
            return response([{"implementation": name.title(), "syncLevel": "fullSync", "fields": [{"name": "baseUrl", "value": f"http://127.0.0.1:{catalog.catalog.get(name).port}"}]} for name in ("sonarr", "radarr") if catalog.catalog.get(name).is_installed()])
        if path.endswith("/indexer"):
            return response([{"enable": True, "name": "Synthetic private provider"}] if state["source"] else [])
        if "/settings/sonarr" in path or "/settings/radarr" in path:
            name = path.rsplit("/", 1)[-1]
            return response([{"hostname": "127.0.0.1", "port": catalog.catalog.get(name).port, "apiKey": "fixture-key", "isDefault": True}])
        return response({})
    requests.get = provider_get

    def snapshot(*args, **kwargs):
        apps = [{"name": p.name, "display_name": p.manifest.display_name, "category": p.manifest.category.value, "port": p.port, "state": "running", "state_label": "", "sick": False, "url": f"http://127.0.0.1:{p.port}"} for p in catalog.catalog.all_plugins() if p.is_installed()]
        item = {"title": "Synthetic Journey", "source": "jellyfin", "mediaType": "tv", "mediaId": 9001, "detail": "Test series", "url": "http://127.0.0.1:8096/web/", "poster": ""}
        trending = [{"title": "Trending Fixture", "source": "seerr", "mediaType": "movie", "mediaId": 9002, "detail": "2026", "status": "missing", "can_request": True, "poster": ""}] if state["trending"] else []
        poster = 'data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A//www.w3.org/2000/svg%22%20viewBox%3D%220%200%202%203%22%3E%3Crect%20width%3D%222%22%20height%3D%223%22%20fill%3D%22%23387%22/%3E%3C/svg%3E'
        recent = [dict(item, title=f"Recent {index}", poster=poster) for index in range(1, 3)] if state["media_widgets"] else ([item] if state["downloaded"] else [])
        requests_list = [{"title": f"Request {index}", "source": "seerr", "mediaType": "movie", "status": "available", "url": "", "poster": poster} for index in range(1, 3)] if state["media_widgets"] else []
        if state["media_widgets"]:
            trending = [{"title": f"Trending {index}", "source": "seerr", "mediaType": "movie", "mediaId": 9000 + index, "detail": "2026", "status": "missing", "can_request": True, "poster": poster} for index in range(1, 3)]
        if state["trending_statuses"]:
            trending = [
                {"title": "Available Trending", "source": "seerr", "mediaType": "movie", "mediaId": 9101, "status": "available", "can_request": False, "poster": ""},
                {"title": "Requested Trending", "source": "seerr", "mediaType": "movie", "mediaId": 9102, "status": "requested", "can_request": False, "poster": ""},
                {"title": "Deleted Trending", "source": "seerr", "mediaType": "tv", "mediaId": 9104, "status": "deleted", "can_request": True, "poster": ""},
                {"title": "Missing Trending", "source": "seerr", "mediaType": "movie", "mediaId": 9103, "status": "missing", "can_request": True, "poster": ""},
            ]
        queue = [{"title": "Synthetic Journey", "source": "qbittorrent", "id": "fixture-download", "progress": 42, "size": 100, "downloaded": 42, "speed": 1000, "eta": 60, "state": "downloading", "moving": True}] if state["requested"] and not state["downloaded"] else []
        calendar = [{"title": "Calendar fixture", "when": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(), "detail": "S01E01", "kind": "episode", "source": "sonarr", "has_file": False, "url": "http://127.0.0.1:8989/series/fixture"}]
        if state["calendar_colors"]:
            calendar.extend([
                {"title": "Radarr fixture", "when": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(), "detail": "2026", "kind": "movie", "source": "radarr", "has_file": False, "url": "http://127.0.0.1:7878/movie/fixture"},
                {"title": "Available fixture", "when": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(), "detail": "2026", "kind": "movie", "source": "radarr", "has_file": True, "url": "http://127.0.0.1:7878/movie/fixture"},
            ])
        return {"apps": apps, "calendar": calendar, "downloads": queue, "recent": recent, "requests": requests_list, "trending": trending, "widgets": [], "waiting": [], "seerr": {"available": True, "url": "http://127.0.0.1:5055"}, "partial": False}
    homepage.homepage_snapshot = snapshot
    homepage.homepage_title = lambda *a, **kw: {"ok": False, "detail": "Synthetic title detail failure"} if state["trending_detail_fail"] else {"ok": True, "title": "Trending Fixture", "overview": "Synthetic title overview", "year": "2026"}
    homepage.sync_seerr_external_links = lambda *a: None
    homepage.homepage_downloads = lambda: {"downloads": snapshot()["downloads"], "widgets": [], "pause": {"paused": False}}
    homepage.homepage_status = lambda *a, **kw: {"playing": [], "server": None, "storage": [], "attention": []}
    homepage.homepage_search = lambda host, q, provider: {"query": q, "seerr": True, "provider": "seerr", "results": [{"title": "Synthetic Journey", "mediaType": "tv", "mediaId": 9001, "source": "seerr", "status": "missing", "can_request": True, "poster": ""}]}
    homepage.homepage_request_options = lambda *a, **kw: {"needsChoice": False, "servers": []}
    def request_title(payload):
        state["requested"] = True
        return {"ok": True, "detail": "Synthetic request submitted"}
    homepage.homepage_request = request_title

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.post("/_test/reset")
    async def reset():
        if backup_jobs._task is not None:
            await backup_jobs.wait()
        for path in root.iterdir():
            if path.is_dir(): shutil.rmtree(path)
            else: path.unlink()
        settings.initialise()
        state.update(wired=False, source=False, requested=False, downloaded=False, fail_update=False, trending=False, trending_detail_fail=False, trending_statuses=False, calendar_colors=False, media_widgets=False, service_status=False, service_status_down=False)
        process_states.clear(); clear_jobs()
        secret_store._fernet = None; secret_store._memory_data.clear()
        auth_manager._rate._hits.clear()
        wizard.wizard_engine = WizardEngine(cfg=settings)
        backup_jobs.job = None; backup_jobs._task = None
        return {"ok": True, "root": str(root)}

    @app.post("/_test/provider-ready")
    def provider_ready():
        state["source"] = True
        return {"ok": True}

    @app.post("/_test/trending")
    def trending_ready():
        state["trending"] = True
        return {"ok": True}

    @app.post("/_test/trending-detail-fail")
    def trending_detail_fail():
        state["trending_detail_fail"] = True
        return {"ok": True}

    @app.post("/_test/trending-statuses")
    def trending_statuses():
        state["trending_statuses"] = True
        return {"ok": True}

    @app.post("/_test/calendar-colors")
    def calendar_colors_ready():
        state["calendar_colors"] = True
        return {"ok": True}

    @app.post("/_test/media-widgets")
    def media_widgets_ready():
        state["media_widgets"] = True
        return {"ok": True}

    @app.post("/_test/service-status")
    def service_status_ready():
        state["service_status"] = True
        state["service_status_down"] = False
        return {"ok": True}

    @app.post("/_test/service-status-down")
    def service_status_down():
        state["service_status_down"] = True
        return {"ok": True}

    @app.post("/_test/complete-download")
    def complete_download():
        if not state["requested"]:
            return {"ok": False}
        downloaded = settings.download_dir / "synthetic.txt"
        downloaded.parent.mkdir(parents=True, exist_ok=True)
        downloaded.write_text("synthetic media fixture")
        imported = settings.media_dir / "tv" / "Synthetic Journey" / "episode.txt"
        imported.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(downloaded, imported)
        state["downloaded"] = True
        return {"ok": True, "imported": imported.is_file()}

    @app.post("/_test/change-preferences")
    def change_preferences():
        (settings.config_dir / "sonarr" / "preferences.json").write_text('{"quality":"changed"}')
        return {"ok": True}

    @app.post("/_test/fail-update")
    def fail_update():
        state["fail_update"] = True
        return {"ok": True}

    @app.get("/_test/state")
    def fixture_state():
        preferences = settings.config_dir / "sonarr" / "preferences.json"
        return {**state, "preferences": json.loads(preferences.read_text()) if preferences.exists() else None}

    @app.get("/health")
    def health(): return {"status": "ok", "version": "fixture", "git_sha": "fixture"}
    @app.get("/api/system/info")
    def system_info():
        info = {"platform": "isolated-test-fixture", "vpn": {"enabled": False}, "metrics": {}, "transcoding": {}, "public_app_hostnames": {}}
        if state["service_status"]:
            info["vpn"] = {"enabled": True, "tunnel_up": True, "handshake_ok": True}
            info["cloudflare_tunnel"] = {"enabled": True, "running": True, "connected": not state["service_status_down"]}
        return info
    @app.get("/api/vpn/status")
    def vpn_status(): return {"enabled": False}
    @app.get("/api/diagnostics")
    def diagnostics(): return {"errors": [], "share": {"active": False}}
    @app.get("/api/homepage/other")
    def other(): return {"items": []}
    @app.get("/api/homepage/recent")
    @app.get("/api/homepage/trending")
    def more(): return {"items": []}
    @app.get("/api/settings")
    def public_settings(request: Request):
        auth_manager.authenticate_request(request)
        return {**settings.as_serialisable_dict(), "updates": updates.scheduler.public_status(), "backups": backup_jobs.public_status(), "storage": {}, "homepage_keys": {}, "branding": {}}

    for module in (auth, wizard, catalog, applications, integrations, homepage, backups, notifications, settings_router, updates):
        app.include_router(module.router)
    app.mount("/", StaticFiles(directory=Path(__file__).resolve().parents[1] / "frontend" / "dist", html=True))
    return app


if __name__ == "__main__":
    import uvicorn
    with tempfile.TemporaryDirectory(prefix="aio-browser-e2e-") as directory:
        uvicorn.run(build_app(Path(directory)), host="127.0.0.1", port=int(os.environ.get("AIO_E2E_PORT", "8765")), log_level="warning")
