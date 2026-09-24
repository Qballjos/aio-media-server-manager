"""Household homepage snapshot, search, and Seerr request helpers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.app import create_app
from core.auth import auth_manager
from core.homepage import homepage_request, homepage_search, homepage_snapshot
from core.settings import Settings


def _plugin(name: str, port: int, config_dir, *, daemon: bool = True, installed: bool = True, display: str | None = None):
    plugin = SimpleNamespace(
        name=name,
        port=port,
        config_dir=config_dir,
        manifest=SimpleNamespace(
            display_name=display or name.title(),
            daemon=daemon,
            category=SimpleNamespace(value="automation"),
        ),
    )
    plugin.is_installed = lambda: installed
    return plugin


class FakeCatalog:
    def __init__(self, plugins: list):
        self._plugins = {plugin.name: plugin for plugin in plugins}

    def all_plugins(self):
        return list(self._plugins.values())

    def has(self, name: str) -> bool:
        return name in self._plugins

    def get(self, name: str):
        return self._plugins[name]


def test_homepage_hides_uninstalled_and_cli_apps(tmp_path):
    catalog = FakeCatalog(
        [
            _plugin("sonarr", 8989, tmp_path),
            _plugin("recyclarr", 19001, tmp_path, daemon=False),
            _plugin("lidarr", 8686, tmp_path, installed=False),
        ]
    )
    with (
        patch("core.homepage.ApplicationCatalog", return_value=catalog),
        patch("core.homepage._running_names", return_value={"sonarr"}),
        patch("core.homepage._get_json", return_value=None),
        patch("core.homepage.get_application_api_key", return_value=None),
    ):
        snap = homepage_snapshot("192.168.2.10")
    names = [item["name"] for item in snap["apps"]]
    assert names == ["sonarr"]
    assert snap["apps"][0]["url"] == "http://192.168.2.10:8989"
    assert snap["apps"][0]["running"] is True
    assert snap["calendar"] == []
    assert snap["downloads"] == []
    assert snap["recent"] == []
    assert snap["seerr"]["available"] is False
    notes = {(item["widget"], item["source"], item["state"]): item["detail"] for item in snap["widgets"]}
    assert notes[("calendar", "sonarr", "error")] == "running but no API key yet"
    assert notes[("calendar", "radarr", "skipped")] == "not installed"
    assert notes[("downloads", "sabnzbd", "skipped")] == "not installed"
    assert notes[("recent", "jellyfin", "skipped")] == "not installed"
    assert notes[("search", "seerr", "skipped")] == "not installed"


def test_homepage_calendar_from_sonarr(tmp_path):
    catalog = FakeCatalog([_plugin("sonarr", 8989, tmp_path)])
    with (
        patch("core.homepage.ApplicationCatalog", return_value=catalog),
        patch("core.homepage._running_names", return_value={"sonarr"}),
        patch("core.homepage.get_application_api_key", return_value="k"),
        patch(
            "core.homepage._fetch_json",
            return_value=(
                [
                    {
                        "title": "Pilot",
                        "seasonNumber": 1,
                        "episodeNumber": 2,
                        "airDateUtc": "2026-09-24T20:00:00Z",
                        "hasFile": False,
                        "series": {"title": "Example Show"},
                    }
                ],
                None,
            ),
        ),
    ):
        snap = homepage_snapshot("host.local")
    assert snap["calendar"][0]["title"] == "Example Show"
    assert "S01E02" in snap["calendar"][0]["detail"]
    assert snap["calendar"][0]["source"] == "sonarr"
    sonarr_note = next(item for item in snap["widgets"] if item["source"] == "sonarr")
    assert sonarr_note["state"] == "ok"
    assert sonarr_note["count"] == 1


def test_homepage_widget_debug_http_error(tmp_path):
    catalog = FakeCatalog([_plugin("sonarr", 8989, tmp_path), _plugin("radarr", 7878, tmp_path)])
    with (
        patch("core.homepage.ApplicationCatalog", return_value=catalog),
        patch("core.homepage._running_names", return_value={"sonarr", "radarr"}),
        patch("core.homepage.get_application_api_key", return_value="k"),
        patch("core.homepage._fetch_json", return_value=(None, "HTTP 401")),
    ):
        snap = homepage_snapshot("host.local")
    assert snap["calendar"] == []
    notes = {item["source"]: item for item in snap["widgets"] if item["widget"] == "calendar"}
    assert notes["sonarr"]["state"] == "error"
    assert notes["sonarr"]["detail"] == "HTTP 401"
    assert notes["radarr"]["detail"] == "HTTP 401"


def test_homepage_widget_debug_stopped_source(tmp_path):
    catalog = FakeCatalog([_plugin("jellyfin", 8096, tmp_path)])
    with (
        patch("core.homepage.ApplicationCatalog", return_value=catalog),
        patch("core.homepage._running_names", return_value=set()),
        patch("core.homepage.get_application_api_key", return_value="k"),
    ):
        snap = homepage_snapshot("host.local")
    jelly = next(item for item in snap["widgets"] if item["source"] == "jellyfin")
    assert jelly["state"] == "skipped"
    assert jelly["detail"] == "stopped"


def test_homepage_search_requires_two_characters():
    assert homepage_search("host", "a")["results"] == []


def test_homepage_search_uses_seerr_when_running(tmp_path):
    catalog = FakeCatalog([_plugin("seerr", 5055, tmp_path)])
    with (
        patch("core.homepage.ApplicationCatalog", return_value=catalog),
        patch("core.homepage._running_names", return_value={"seerr"}),
        patch("core.homepage.get_application_api_key", return_value="k"),
        patch(
            "core.homepage._get_json",
            return_value={
                "results": [
                    {"id": 42, "mediaType": "movie", "title": "Dune", "releaseDate": "2021-01-01", "posterPath": "/x.jpg"}
                ]
            },
        ),
    ):
        data = homepage_search("host", "dune")
    assert data["seerr"] is True
    assert data["results"][0]["can_request"] is True
    assert data["results"][0]["mediaId"] == 42
    assert "image.tmdb.org" in data["results"][0]["poster"]


def test_homepage_request_without_seerr(tmp_path):
    catalog = FakeCatalog([_plugin("sonarr", 8989, tmp_path)])
    with (
        patch("core.homepage.ApplicationCatalog", return_value=catalog),
        patch("core.homepage._running_names", return_value={"sonarr"}),
    ):
        result = homepage_request({"mediaType": "movie", "mediaId": 1})
    assert result["ok"] is False


def test_homepage_api_requires_session(tmp_path, monkeypatch):
    test_settings = Settings(
        config_dir=tmp_path / "config",
        download_dir=tmp_path / "downloads",
        media_dir=tmp_path / "media",
        install_dir=tmp_path / "apps",
    )
    test_settings.initialise()
    monkeypatch.setattr(auth_manager, "_settings", test_settings)
    auth_manager._rate._hits.clear()
    client = TestClient(create_app())
    setup = client.post(
        "/api/auth/setup",
        json={"username": "admin", "email": "admin@example.com", "password": "StrongPassword123!"},
    )
    assert setup.status_code == 200
    client.cookies.clear()
    denied = client.get("/api/homepage")
    assert denied.status_code in (401, 403)

    token = setup.json()["access_token"]
    csrf = setup.json()["csrf_token"]
    with patch("api.routers.homepage.homepage_snapshot", return_value={"apps": [], "calendar": [], "downloads": [], "recent": [], "seerr": {"available": False, "url": None}}):
        ok = client.get(
            "/api/homepage",
            headers={"Authorization": f"Bearer {token}", "X-CSRF-Token": csrf},
        )
    assert ok.status_code == 200
    assert ok.json()["apps"] == []
