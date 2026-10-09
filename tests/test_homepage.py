"""Household homepage snapshot, search, and Seerr request helpers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from datetime import date
import threading

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from core.auth import auth_manager
from core.homepage import (
    calendar_fetch_span,
    clear_homepage_snapshot_cache,
    collapse_full_seasons,
    homepage_downloads,
    homepage_request,
    homepage_search,
    homepage_snapshot,
    month_calendar_span,
)
from core.settings import Settings


def _plugin(name: str, port: int, config_dir, *, daemon: bool = True, installed: bool = True, display: str | None = None, category: str = "automation"):
    plugin = SimpleNamespace(
        name=name,
        port=port,
        config_dir=config_dir,
        manifest=SimpleNamespace(
            display_name=display or name.title(),
            daemon=daemon,
            category=SimpleNamespace(value=category),
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


@pytest.fixture(autouse=True)
def _clear_homepage_cache():
    clear_homepage_snapshot_cache()
    yield
    clear_homepage_snapshot_cache()


def test_calendar_fetch_span_covers_adjacent_months():
    start, end = calendar_fetch_span(date(2026, 9, 30))
    assert start == date(2026, 7, 27)
    assert start.weekday() == 0
    assert end == date(2026, 11, 1)
    assert end.weekday() == 6
    assert start < date(2026, 8, 1) <= date(2026, 10, 31) < end


def test_month_calendar_span_is_monday_to_sunday():
    start, end = month_calendar_span(date(2026, 9, 24))
    assert start == date(2026, 8, 31)
    assert start.weekday() == 0
    assert end == date(2026, 10, 4)
    assert end.weekday() == 6


def test_homepage_public_urls_use_subdomains(tmp_path, monkeypatch):
    from core.public_hostnames import save_hostnames
    from core.settings import settings as live_settings

    cfg = Settings(
        config_dir=tmp_path / "config",
        download_dir=tmp_path / "dl",
        media_dir=tmp_path / "media",
        public_app_base_domain="example.com",
    )
    save_hostnames({"sonarr": {"subdomain": "tv", "enabled": True}}, app_settings=cfg)
    monkeypatch.setattr("core.app_web_url.settings", cfg)
    monkeypatch.setattr("core.public_hostnames.settings", cfg)
    monkeypatch.setattr(live_settings, "public_app_base_domain", "example.com")
    monkeypatch.setattr(live_settings, "config_dir", cfg.config_dir)

    catalog = FakeCatalog([_plugin("sonarr", 8989, tmp_path)])
    with patch("core.homepage.ApplicationCatalog", return_value=catalog), patch(
        "core.homepage._running_names", return_value={"sonarr"}
    ), patch("core.homepage._process_states", return_value={}):
        snap = homepage_snapshot("media.example.com", force=True, scheme="https")
    assert snap["apps"][0]["url"] == "https://tv.example.com"


def test_homepage_snapshot_reuses_memory_cache(tmp_path):
    catalog = FakeCatalog([_plugin("sonarr", 8989, tmp_path)])
    calls = {"n": 0}

    def fake_fetch(*_args, **_kwargs):
        calls["n"] += 1
        return ([], None)

    with (
        patch("core.homepage.ApplicationCatalog", return_value=catalog),
        patch("core.homepage._running_names", return_value={"sonarr"}),
        patch("core.homepage.get_application_api_key", return_value="k"),
        patch("core.homepage._fetch_json", side_effect=fake_fetch),
    ):
        first = homepage_snapshot("nas.local", force=True)
        second = homepage_snapshot("nas.local")
        forced = homepage_snapshot("nas.local", force=True)
        other_host = homepage_snapshot("other.local", force=True)
    assert first["calendar"] == second["calendar"]
    assert calls["n"] == 3
    assert forced["apps"][0]["url"].startswith("http://nas.local:")
    assert other_host["apps"][0]["url"].startswith("http://other.local:")


def test_homepage_cold_miss_returns_launcher_immediately(tmp_path, monkeypatch):
    catalog = FakeCatalog([_plugin("sonarr", 8989, tmp_path)])
    started = []
    real_thread = threading.Thread

    def fake_thread(*args, **kwargs):
        name = kwargs.get("name") or ""
        if str(name).startswith("homepage-refresh-"):
            started.append(kwargs.get("target"))
            return SimpleNamespace(start=lambda: None)
        return real_thread(*args, **kwargs)

    with (
        patch("core.homepage.ApplicationCatalog", return_value=catalog),
        patch("core.homepage._running_names", return_value={"sonarr"}),
        patch("core.homepage.get_application_api_key", return_value="k"),
        patch("core.homepage._fetch_json", return_value=([], None)),
        patch("threading.Thread", side_effect=fake_thread),
    ):
        snap = homepage_snapshot("nas.local")
    assert snap["apps"]
    assert snap.get("partial") is True
    assert snap["calendar"] == []
    assert started



def test_homepage_stale_snapshot_returns_immediately(tmp_path, monkeypatch):
    catalog = FakeCatalog([_plugin("sonarr", 8989, tmp_path)])
    monkeypatch.setattr("core.homepage._CACHE_TTL", 0.0)
    started = []
    real_thread = threading.Thread

    def fake_thread(*args, **kwargs):
        name = kwargs.get("name") or ""
        if str(name).startswith("homepage-refresh-"):
            started.append(kwargs.get("target"))
            return SimpleNamespace(start=lambda: None)
        return real_thread(*args, **kwargs)

    with (
        patch("core.homepage.ApplicationCatalog", return_value=catalog),
        patch("core.homepage._running_names", return_value={"sonarr"}),
        patch("core.homepage.get_application_api_key", return_value="k"),
        patch("core.homepage._fetch_json", return_value=([], None)),
        patch("threading.Thread", side_effect=fake_thread),
    ):
        homepage_snapshot("nas.local")
        homepage_snapshot("nas.local")
    from core import homepage as homepage_mod

    assert started == [homepage_mod._refresh_snapshot]


def test_homepage_hides_uninstalled_and_cli_apps(tmp_path):
    catalog = FakeCatalog(
        [
            _plugin("sonarr", 8989, tmp_path),
            _plugin("recyclarr", 19001, tmp_path, daemon=False),
            _plugin("flaresolverr", 8191, tmp_path, category="indexers"),
            _plugin("lidarr", 8686, tmp_path, installed=False),
        ]
    )
    with (
        patch("core.homepage.ApplicationCatalog", return_value=catalog),
        patch("core.homepage._running_names", return_value={"sonarr"}),
        patch("core.homepage._get_json", return_value=None),
        patch("core.homepage.get_application_api_key", return_value=None),
    ):
        snap = homepage_snapshot("192.168.2.10", force=True)
    names = [item["name"] for item in snap["apps"]]
    assert names == ["sonarr"]
    assert snap["apps"][0]["url"] == "http://192.168.2.10:8989"
    assert snap["apps"][0]["running"] is True
    assert snap["apps"][0]["sick"] is False
    assert snap["apps"][0]["category"] == "automation"
    assert snap["calendar"] == []
    assert snap["downloads"] == []
    assert snap["recent"] == []
    assert snap["requests"] == []
    assert snap["trending"] == []
    assert snap["seerr"]["available"] is False
    notes = {(item["widget"], item["source"], item["state"]): item["detail"] for item in snap["widgets"]}
    assert notes[("calendar", "sonarr", "error")] == "running but no API key yet"
    assert notes[("calendar", "radarr", "skipped")] == "not installed"
    assert notes[("downloads", "sabnzbd", "skipped")] == "not installed"
    assert notes[("recent", "jellyfin", "skipped")] == "not installed"
    assert notes[("trending", "seerr", "skipped")] == "not installed"
    assert notes[("search", "seerr", "skipped")] == "not installed"


def test_homepage_launcher_groups_by_category(tmp_path):
    catalog = FakeCatalog(
        [
            _plugin("sonarr", 8989, tmp_path, category="automation"),
            _plugin("jellyfin", 8096, tmp_path, category="media"),
            _plugin("seerr", 5055, tmp_path, category="requests"),
            _plugin("flaresolverr", 8191, tmp_path, category="indexers"),
        ]
    )
    with (
        patch("core.homepage.ApplicationCatalog", return_value=catalog),
        patch("core.homepage._running_names", return_value={"sonarr", "jellyfin", "seerr", "flaresolverr"}),
        patch("core.homepage.get_application_api_key", return_value=None),
        patch("core.homepage._fetch_json", return_value=(None, "skipped")),
    ):
        snap = homepage_snapshot("nas.local")
    assert [item["name"] for item in snap["apps"]] == ["jellyfin", "seerr", "sonarr"]
    assert [item["category"] for item in snap["apps"]] == ["media", "requests", "automation"]


def test_homepage_launcher_marks_crash_loop_sick(tmp_path):
    catalog = FakeCatalog(
        [
            _plugin("sonarr", 8989, tmp_path),
            _plugin("radarr", 7878, tmp_path),
        ]
    )
    clear_homepage_snapshot_cache()
    with (
        patch("core.homepage.ApplicationCatalog", return_value=catalog),
        patch("core.homepage._running_names", return_value={"radarr"}),
        patch(
            "core.homepage._process_states",
            return_value={
                "sonarr": {"name": "sonarr", "state": "crash_loop", "is_crash_loop": True},
                "radarr": {"name": "radarr", "state": "running", "is_crash_loop": False},
            },
        ),
        patch("core.homepage.get_application_api_key", return_value=None),
        patch("core.homepage._fetch_json", return_value=(None, "skipped")),
    ):
        snap = homepage_snapshot("crash-loop.local")
    by_name = {item["name"]: item for item in snap["apps"]}
    assert by_name["sonarr"]["running"] is False
    assert by_name["sonarr"]["sick"] is True
    assert by_name["radarr"]["running"] is True
    assert by_name["radarr"]["sick"] is False


def test_homepage_downloads_include_speed(tmp_path):
    catalog = FakeCatalog([_plugin("sabnzbd", 8085, tmp_path, category="downloading")])
    with (
        patch("core.homepage.ApplicationCatalog", return_value=catalog),
        patch("core.homepage._running_names", return_value={"sabnzbd"}),
        patch("core.homepage.get_application_api_key", return_value="k"),
        patch(
            "core.homepage._fetch_json",
            return_value=(
                {
                    "queue": {
                        "kbpersec": "1500.0",
                        "slots": [
                            {
                                "filename": "Show.nzb",
                                "status": "Downloading",
                                "percentage": "42.2",
                                "kbpersec": "1500.0",
                                "timeleft": "0:12:04",
                            }
                        ],
                    }
                },
                None,
            ),
        ),
    ):
        data = homepage_downloads()
        snap = homepage_snapshot("nas.local", force=True)
    item = data["downloads"][0]
    assert item["title"] == "Show.nzb"
    assert item["progress"] == 42
    assert item["speed_bps"] == 1_500_000
    assert item["eta"] == "0:12:04"
    assert snap["downloads"][0]["speed_bps"] == 1_500_000


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
        snap = homepage_snapshot("host.local", force=True)
    assert snap["calendar"][0]["title"] == "Example Show"
    assert "S01E02" in snap["calendar"][0]["detail"]
    assert "Pilot" in snap["calendar"][0]["detail"]
    assert snap["calendar"][0]["has_file"] is False
    assert snap["calendar"][0]["when"].startswith("2026-09-24T20:00:00")
    assert snap["calendar"][0]["source"] == "sonarr"
    sonarr_note = next(item for item in snap["widgets"] if item["source"] == "sonarr")
    assert sonarr_note["state"] == "ok"
    assert sonarr_note["count"] == 1


def test_homepage_jellyfin_recent_has_poster_proxy(tmp_path):
    catalog = FakeCatalog([_plugin("jellyfin", 8096, tmp_path)])
    with (
        patch("core.homepage.ApplicationCatalog", return_value=catalog),
        patch("core.homepage._running_names", return_value={"jellyfin"}),
        patch("core.homepage.get_application_api_key", return_value="k"),
        patch(
            "core.homepage._fetch_json",
            return_value=(
                {"Items": [{"Id": "abc", "Name": "Dune", "Type": "Movie", "ProductionYear": 2021, "DateCreated": "2026-09-01"}]},
                None,
            ),
        ),
    ):
        snap = homepage_snapshot("nas.local", force=True)
    assert snap["recent"][0]["title"] == "Dune"
    assert snap["recent"][0]["poster"].startswith("/api/homepage/art?source=jellyfin")
    assert "abc" in snap["recent"][0]["poster"]


def _episode(series: str, season: int, episode: int, when: str, **extra):
    item = {
        "source": "jellyfin",
        "title": series,
        "detail": f"S{season:02d}E{episode:02d}",
        "when": when,
        "poster": "/p",
        "url": f"http://nas/web/#/details?id=e{episode}",
        "_kind": "episode",
        "_series_id": series,
        "_season": season,
        "_episode": episode,
        "_season_id": "season-1",
    }
    item.update(extra)
    return item


def test_collapse_full_season_hides_member_episodes():
    when = "2026-09-30T20:00:00"
    rows = [_episode("Severance", 1, n, when) for n in range(1, 5)]
    rows.append(
        {
            "source": "jellyfin",
            "title": "Dune",
            "detail": "2021",
            "when": "2026-09-29T12:00:00",
            "poster": "/dune",
            "url": "http://nas/web/#/details?id=dune",
            "_kind": "movie",
        }
    )
    out = collapse_full_seasons(rows)
    assert [item["title"] for item in out] == ["Severance", "Dune"]
    assert out[0]["detail"] == "Season 01"
    assert out[0]["url"].endswith("id=season-1")


def test_collapse_keeps_single_and_partial_season_episodes():
    rows = [
        _episode("Show", 1, 4, "2026-09-30T20:00:00"),
        _episode("Show", 1, 5, "2026-09-30T20:01:00"),
        _episode("Other", 2, 1, "2026-09-29T18:00:00"),
        _episode("Show", 1, 6, "2026-09-20T10:00:00"),
    ]
    out = collapse_full_seasons(rows)
    details = [item["detail"] for item in out]
    assert details == ["S01E05", "S01E04", "S02E01", "S01E06"]


def test_homepage_jellyfin_full_season_is_one_tile(tmp_path):
    catalog = FakeCatalog([_plugin("jellyfin", 8096, tmp_path)])
    items = [
        {
            "Id": f"e{n}",
            "Type": "Episode",
            "Name": f"Episode {n}",
            "SeriesName": "Severance",
            "SeriesId": "show1",
            "ParentId": "s1",
            "ParentIndexNumber": 1,
            "IndexNumber": n,
            "DateCreated": "2026-09-30T20:00:00",
        }
        for n in range(1, 5)
    ]
    with (
        patch("core.homepage.ApplicationCatalog", return_value=catalog),
        patch("core.homepage._running_names", return_value={"jellyfin"}),
        patch("core.homepage.get_application_api_key", return_value="k"),
        patch("core.homepage._fetch_json", return_value=({"Items": items}, None)),
    ):
        snap = homepage_snapshot("nas.local", force=True)
    assert len(snap["recent"]) == 1
    assert snap["recent"][0]["title"] == "Severance"
    assert snap["recent"][0]["detail"] == "Season 01"


def test_homepage_seerr_requests_row(tmp_path):
    catalog = FakeCatalog([_plugin("seerr", 5055, tmp_path)])

    def fake_fetch(url, **_kwargs):
        if "/request" in url and "/discover/" not in url:
            return (
                {
                    "results": [
                        {
                            "media": {"tmdbId": 42, "mediaType": "movie", "status": 2},
                            "requestedBy": {"displayName": "Qballjos"},
                        }
                    ]
                },
                None,
            )
        if "/discover/trending" in url:
            return ({"results": []}, None)
        if "/movie/42" in url:
            return ({"title": "Dune", "posterPath": "/x.jpg"}, None)
        return (None, "unexpected")

    with (
        patch("core.homepage.ApplicationCatalog", return_value=catalog),
        patch("core.homepage._running_names", return_value={"seerr"}),
        patch("core.homepage.get_application_api_key", return_value="k"),
        patch("core.homepage._fetch_json", side_effect=fake_fetch),
    ):
        snap = homepage_snapshot("nas.local", force=True)
    assert snap["requests"][0]["title"] == "Dune"
    assert snap["requests"][0]["detail"] == "Qballjos"
    assert snap["requests"][0]["mediaType"] == "movie"
    assert snap["requests"][0]["status"] == "requested"
    assert "image.tmdb.org" in snap["requests"][0]["poster"]


def test_homepage_seerr_trending_row(tmp_path):
    catalog = FakeCatalog([_plugin("seerr", 5055, tmp_path)])

    def fake_fetch(url, **_kwargs):
        if "/discover/trending" in url:
            return (
                {
                    "results": [
                        {
                            "id": 99,
                            "mediaType": "movie",
                            "title": "Trending Hit",
                            "posterPath": "/t.jpg",
                            "releaseDate": "2026-01-15",
                            "mediaInfo": {"status": 1},
                        },
                        {
                            "id": 7,
                            "mediaType": "tv",
                            "name": "Hot Show",
                            "posterPath": "/s.jpg",
                            "firstAirDate": "2025-05-01",
                            "mediaInfo": {"status": 5},
                        },
                        {"id": 3, "mediaType": "person", "name": "Someone"},
                    ]
                },
                None,
            )
        if "/request" in url:
            return ({"results": []}, None)
        return (None, "unexpected")

    with (
        patch("core.homepage.ApplicationCatalog", return_value=catalog),
        patch("core.homepage._running_names", return_value={"seerr"}),
        patch("core.homepage.get_application_api_key", return_value="k"),
        patch("core.homepage._fetch_json", side_effect=fake_fetch),
    ):
        snap = homepage_snapshot("nas.local", force=True)
    assert len(snap["trending"]) == 2
    assert snap["trending"][0]["title"] == "Trending Hit"
    assert snap["trending"][0]["detail"] == "2026"
    assert snap["trending"][0]["can_request"] is True
    assert snap["trending"][0]["mediaId"] == 99
    assert "image.tmdb.org" in snap["trending"][0]["poster"]
    assert snap["trending"][1]["title"] == "Hot Show"
    assert snap["trending"][1]["can_request"] is False
    assert snap["trending"][1]["status"] == "available"


def test_homepage_widget_debug_http_error(tmp_path):
    catalog = FakeCatalog([_plugin("sonarr", 8989, tmp_path), _plugin("radarr", 7878, tmp_path)])
    with (
        patch("core.homepage.ApplicationCatalog", return_value=catalog),
        patch("core.homepage._running_names", return_value={"sonarr", "radarr"}),
        patch("core.homepage.get_application_api_key", return_value="k"),
        patch("core.homepage._fetch_json", return_value=(None, "HTTP 401")),
    ):
        snap = homepage_snapshot("host.local", force=True)
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
        snap = homepage_snapshot("host.local", force=True)
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
            "core.homepage._fetch_json",
            return_value=(
                {
                    "results": [
                        {"id": 42, "mediaType": "movie", "title": "Dune", "releaseDate": "2021-01-01", "posterPath": "/x.jpg"},
                        {"id": 7, "mediaType": "tv", "name": "Dune: Prophecy", "mediaInfo": {"status": 5}},
                        {"id": 9, "mediaType": "person", "name": "Denis Villeneuve"},
                    ]
                },
                None,
            ),
        ) as fetch,
    ):
        data = homepage_search("host", "dune part two")
    assert "query=dune%20part%20two" in fetch.call_args.args[0]
    assert data["seerr"] is True
    assert data["error"] is None
    assert len(data["results"]) == 2
    assert data["results"][0]["can_request"] is True
    assert data["results"][0]["status"] == "missing"
    assert data["results"][0]["mediaId"] == 42
    assert "image.tmdb.org" in data["results"][0]["poster"]
    assert data["results"][1]["status"] == "available"
    assert data["results"][1]["can_request"] is False


def test_homepage_search_falls_back_when_seerr_rejects_key(tmp_path):
    catalog = FakeCatalog([_plugin("seerr", 5055, tmp_path), _plugin("radarr", 7878, tmp_path)])
    with (
        patch("core.homepage.ApplicationCatalog", return_value=catalog),
        patch("core.homepage._running_names", return_value={"seerr", "radarr"}),
        patch("core.homepage.get_application_api_key", return_value="k"),
        patch("core.homepage._fetch_json", return_value=(None, "HTTP 401")),
        patch(
            "core.homepage._get_json",
            return_value=[{"tmdbId": 1, "id": 3, "hasFile": True, "title": "Dune", "year": 2021}],
        ),
    ):
        data = homepage_search("host", "dune")
    assert data["seerr"] is False
    assert "401" in data["error"]
    assert data["results"][0]["status"] == "available"


def test_seerr_media_status_mapping():
    from core.homepage import seerr_media_status

    assert seerr_media_status({}) == "missing"
    assert seerr_media_status({"mediaInfo": {"status": 2}}) == "requested"
    assert seerr_media_status({"mediaInfo": {"status": 4}}) == "partial"
    assert seerr_media_status({"mediaInfo": {"status": 5}}) == "available"
    assert seerr_media_status({"status": 2}) == "requested"
    assert seerr_media_status({"status": 5}) == "available"


def test_jellyfin_auth_header_carries_token():
    from core.integrations.jellyfin import jellyfin_auth_headers

    headers = jellyfin_auth_headers("abc123")
    assert 'Token="abc123"' in headers["Authorization"]
    assert headers["X-Emby-Token"] == "abc123"


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


def test_homepage_launcher_explains_why_apps_are_stopped(tmp_path, monkeypatch):
    from core.install_jobs import clear_jobs, set_job
    from core.settings import settings

    catalog = FakeCatalog(
        [
            _plugin("prowlarr", 9696, tmp_path, category="indexers"),
            _plugin("seerr", 5055, tmp_path, category="requests"),
            _plugin("sonarr", 8989, tmp_path),
            _plugin("radarr", 7878, tmp_path),
            _plugin("jellyfin", 8096, tmp_path, category="media"),
        ]
    )
    clear_jobs()
    set_job("seerr", "installing")
    set_job("radarr", "configuring")  # process already runs, post-install wiring still busy
    monkeypatch.setattr(settings, "vpn_enabled", True)
    with (
        patch("core.homepage.ApplicationCatalog", return_value=catalog),
        patch("core.homepage._running_names", return_value={"radarr", "jellyfin"}),
        patch("core.homepage.vpn_manager.tunneled_apps_allowed", return_value=False),
        patch("core.homepage.vpn_manager.status", return_value={"tunnel_up": False, "last_error": "handshake timed out"}),
        patch("core.homepage.get_application_api_key", return_value=None),
        patch("core.homepage._fetch_json", return_value=(None, "skipped")),
    ):
        snap = homepage_snapshot("nas.local", force=True)
    clear_jobs()
    by_name = {item["name"]: (item["state"], item["state_label"]) for item in snap["apps"]}
    assert by_name["prowlarr"] == ("waiting_for_vpn", "Waiting for VPN")
    assert by_name["seerr"] == ("installing", "Installing…")
    assert by_name["sonarr"] == ("stopped", "Stopped")
    assert by_name["radarr"] == ("configuring", "Configuring…")
    assert by_name["jellyfin"] == ("running", "")
    assert snap["vpn"] == {
        "enabled": True,
        "tunnel_up": False,
        "waiting": ["prowlarr"],
        "last_error": "handshake timed out",
    }
