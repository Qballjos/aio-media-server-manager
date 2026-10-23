"""Home's status widgets: now playing, storage, server and what needs attention."""

from __future__ import annotations

from collections import namedtuple
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from api.app import create_app
from api.routers import settings as settings_api
from core import homepage_status as status_mod
from core import notifications as notifications_mod
from core import profile as profile_mod
from core import settings as settings_mod
from core.auth import auth_manager
from core.settings import Settings

WEB = "http://nas:8096"
GB = 1024**3


def test_jellyfin_sessions_become_playing_rows():
    rows = [
        {
            "UserName": "ramon",
            "DeviceName": "Living room TV",
            "Client": "Jellyfin Android TV",
            "NowPlayingItem": {
                "Id": "e1",
                "Type": "Episode",
                "Name": "Chapter 3",
                "SeriesName": "Lupin",
                "SeriesId": "s1",
                "ParentIndexNumber": 3,
                "IndexNumber": 3,
                "RunTimeTicks": 30_000_000_000,
            },
            "PlayState": {"PositionTicks": 12_000_000_000, "IsPaused": False, "PlayMethod": "Transcode"},
        },
        {
            "UserName": "jos",
            "Client": "Jellyfin Web",
            "NowPlayingItem": {"Id": "m1", "Type": "Movie", "Name": "Dune", "ProductionYear": 2021, "RunTimeTicks": 0},
            "PlayState": {"PositionTicks": 5, "IsPaused": True, "PlayMethod": "DirectPlay"},
        },
        {"UserName": "idle", "DeviceName": "Web"},
        "not a session",
    ]
    assert status_mod.parse_jellyfin_sessions(rows, WEB) == [
        {
            "source": "jellyfin",
            "user": "ramon",
            "device": "Living room TV",
            "title": "Lupin",
            "detail": "S03E03 · Chapter 3",
            "poster": "/api/homepage/art?source=jellyfin&item_id=s1",
            "url": f"{WEB}/web/#/details?id=e1",
            "progress": 40,
            "paused": False,
            "transcoding": True,
            "minutes_left": 30,
        },
        {
            "source": "jellyfin",
            "user": "jos",
            "device": "Jellyfin Web",
            "title": "Dune",
            "detail": "2021",
            "poster": "/api/homepage/art?source=jellyfin&item_id=m1",
            "url": f"{WEB}/web/#/details?id=m1",
            "progress": 0,
            "paused": True,
            "transcoding": False,
            "minutes_left": None,
        },
    ]
    assert status_mod.parse_jellyfin_sessions({"oops": True}, WEB) == []


def test_plex_sessions_become_playing_rows():
    payload = {
        "MediaContainer": {
            "Metadata": [
                {
                    "type": "episode",
                    "ratingKey": "101",
                    "grandparentRatingKey": "100",
                    "grandparentTitle": "Slow Horses",
                    "title": "Negotiating with Tigers",
                    "parentIndex": 5,
                    "index": 2,
                    "duration": 3_000_000,
                    "viewOffset": 750_000,
                    "User": {"title": "ramon"},
                    "Player": {"title": "Apple TV", "state": "playing", "product": "Plex for Apple TV"},
                    "TranscodeSession": {"videoDecision": "transcode"},
                },
                {
                    "type": "movie",
                    "ratingKey": "200",
                    "title": "Past Lives",
                    "year": 2023,
                    "duration": 6_000_000,
                    "viewOffset": 3_000_000,
                    "User": {"title": "jos"},
                    "Player": {"state": "paused", "product": "Plex Web"},
                },
            ]
        }
    }
    rows = status_mod.parse_plex_sessions(payload, "http://nas:32400")
    assert [(r["title"], r["detail"], r["user"], r["device"]) for r in rows] == [
        ("Slow Horses", "S05E02 · Negotiating with Tigers", "ramon", "Apple TV"),
        ("Past Lives", "2023", "jos", "Plex Web"),
    ]
    assert [(r["progress"], r["paused"], r["transcoding"], r["minutes_left"]) for r in rows] == [(25, False, True, 38), (50, True, False, 50)]
    assert rows[0]["poster"] == "/api/homepage/art?source=plex&item_id=100"
    assert status_mod.parse_plex_sessions(None, "http://nas:32400") == []


def test_storage_volumes_group_paths_on_one_disk_and_skip_missing_ones(tmp_path: Path):
    downloads, media, config = tmp_path / "downloads", tmp_path / "media", tmp_path / "config"
    downloads.mkdir()
    media.mkdir()
    devices = {str(downloads): 7, str(media): 7}
    Usage = namedtuple("Usage", "total used free percent")
    volumes = status_mod.storage_volumes(
        {"Config": config, "Downloads": downloads, "Media": media},
        stat=lambda path: SimpleNamespace(st_dev=devices[str(path)]),
        usage=lambda path: Usage(8000 * GB, 7480 * GB, 520 * GB, 93.5),
        partitions=[],
    )
    assert volumes == [{"labels": ["Downloads", "Media"], "total": 8000 * GB, "used": 7480 * GB, "free": 520 * GB, "percent": 93.5}]


def test_storage_volumes_follow_the_mount_table_across_subvolumes(tmp_path: Path):
    """On a Synology every shared folder is its own btrfs subvolume (own st_dev) on one disk."""
    paths = {}
    for name in ("config", "downloads", "media"):
        (tmp_path / name).mkdir()
        paths[name.title()] = tmp_path / name
    Usage = namedtuple("Usage", "total used free percent")
    st_dev = {str(path): number for number, path in enumerate(paths.values())}
    mounts = [
        SimpleNamespace(device="overlay", mountpoint="/"),
        SimpleNamespace(device="/dev/mapper/cachedev_0", mountpoint=str(paths["Config"])),
        SimpleNamespace(device="/dev/mapper/cachedev_0", mountpoint=str(paths["Downloads"])),
        SimpleNamespace(device="/dev/sdq1", mountpoint=str(paths["Media"])),
    ]
    volumes = status_mod.storage_volumes(
        paths,
        stat=lambda path: SimpleNamespace(st_dev=st_dev[str(path)]),
        usage=lambda path: Usage(100 * GB, 50 * GB, 50 * GB, 50.0),
        partitions=mounts,
    )
    assert [volume["labels"] for volume in volumes] == [["Config", "Downloads"], ["Media"]]


def test_server_summary_reads_cpu_memory_uptime_and_the_hottest_sensor():
    metrics = {
        "cpu_percent": 12.5,
        "cpu_count": 4,
        "memory": {"total": 16 * GB, "available": 10 * GB, "percent": 37.5},
        "network": {"bytes_sent": 2_000, "bytes_recv": 9_000_000},
        "temperatures": {"coretemp": [{"label": "Core 0", "current": 51.0}, {"label": "Core 1", "current": 55.5}]},
    }
    assert status_mod.server_summary(metrics, boot_time=1000.0, now=1000.0 + 3 * 86400) == {
        "cpu_percent": 12.5,
        "cpu_count": 4,
        "memory_percent": 37.5,
        "memory_used": 6 * GB,
        "memory_total": 16 * GB,
        "uptime_seconds": 3 * 86400,
        "temperature": 55.5,
        "network": {"rx_bytes": 9_000_000, "tx_bytes": 2_000},
        "sampled_at": 1000.0 + 3 * 86400,
    }
    empty = status_mod.server_summary({}, boot_time=0, now=10)
    assert empty["temperature"] is None
    assert empty["network"] == {"rx_bytes": 0, "tx_bytes": 0}


def test_attention_lists_problems_first_then_full_disks_then_updates():
    snap = {
        "sick_apps": {"sonarr": "crash_loop", "bazarr": "failed"},
        "vpn_up": False,
        "tunnel_up": None,
        "updates": ["Radarr 5.1", "Sonarr 4.0.10", "Bazarr 1.5", "Appliance image"],
    }
    volumes = [
        {"labels": ["Downloads", "Media"], "total": 8000 * GB, "used": 7880 * GB, "free": 120 * GB, "percent": 93.4},
        {"labels": ["Config"], "total": 100 * GB, "used": 40 * GB, "free": 60 * GB, "percent": 40.0},
    ]
    items = status_mod.attention_items(snap, {"sonarr": "Sonarr", "bazarr": "Bazarr"}, volumes)
    assert [(i["level"], i["title"]) for i in items] == [
        ("problem", "Bazarr failed to start"),
        ("problem", "Sonarr keeps crashing"),
        ("problem", "VPN is not connected"),
        ("warning", "Downloads · Media is 93% full"),
        ("info", "4 updates available"),
    ]
    assert items[0]["href"] == "#/catalog?q=bazarr"
    assert items[3]["detail"] == "120 GB free"
    assert items[4]["detail"] == "Radarr 5.1, Sonarr 4.0.10, Bazarr 1.5 and 1 more"
    assert status_mod.attention_items({"sick_apps": {}, "vpn_up": True, "tunnel_up": True, "updates": []}, {}, volumes[1:]) == []


def test_status_route_needs_a_session_and_returns_every_part(tmp_path: Path, monkeypatch):
    test_settings = Settings(
        config_dir=tmp_path / "config",
        download_dir=tmp_path / "downloads",
        media_dir=tmp_path / "media",
        install_dir=tmp_path / "apps",
    )
    test_settings.initialise()
    for folder in ("downloads", "media"):
        (tmp_path / folder).mkdir(exist_ok=True)
    for module in (settings_api, settings_mod, profile_mod, status_mod, notifications_mod):
        monkeypatch.setattr(module, "settings", test_settings)
    monkeypatch.setattr(auth_manager, "_settings", test_settings)
    monkeypatch.setattr(status_mod, "_attention_cache", None)
    auth_manager._rate._hits.clear()
    client = TestClient(create_app())
    # Before the admin exists the host's numbers are not for anyone on the network, like /api/system/info.
    assert client.get("/api/homepage/status").status_code == 401
    token = client.post(
        "/api/auth/setup",
        json={"username": "admin", "email": "admin@example.com", "password": "StrongPassword123!"},
    ).json()["access_token"]
    client.cookies.clear()
    assert client.get("/api/homepage/status").status_code == 401
    body = client.get("/api/homepage/status", headers={"Authorization": f"Bearer {token}"}).json()
    assert set(body) == {"playing", "server", "storage", "attention"}
    assert body["playing"] == []
    assert body["server"]["memory_total"] > 0
    assert {label for volume in body["storage"] for label in volume["labels"]} == {"Config", "Downloads", "Media"}


def test_attention_never_writes_into_the_data_folders(monkeypatch):
    """The notifications snapshot's disk check writes a test file; Home asks every few seconds and does not need it."""
    from core.storage import StorageManager

    calls = []
    monkeypatch.setattr(StorageManager, "validate_all", lambda self: calls.append(self) or {})
    monkeypatch.setattr(status_mod, "_attention_cache", None)
    snap = status_mod._attention_snapshot()
    assert set(snap) >= {"sick_apps", "vpn_up", "tunnel_up", "updates"}
    assert calls == [], "validate_all writes a test file into config, downloads and media"


def test_now_playing_leaves_finding_the_jellyfin_key_to_the_home_snapshot(tmp_path: Path, monkeypatch):
    """Without a stored key, discovery logs in to Jellyfin (and may restart it); the status poll must not do that."""
    from core.crypto import secret_store
    from core.integrations import jellyfin as jellyfin_mod

    plugin = SimpleNamespace(name="jellyfin", port=8096, config_dir=tmp_path / "jellyfin", is_installed=lambda: True)
    catalog = SimpleNamespace(has=lambda name: name == "jellyfin", get=lambda name: plugin)
    discovered = []
    monkeypatch.setattr(status_mod, "ApplicationCatalog", lambda: catalog)
    monkeypatch.setattr(status_mod, "_running_names", lambda: {"jellyfin"})
    monkeypatch.setattr(secret_store, "get_secret", lambda name: None)
    monkeypatch.setattr(jellyfin_mod, "discover_jellyfin_api_key", lambda *args, **kwargs: discovered.append(args) or None)
    assert status_mod.now_playing("nas") == []
    assert discovered == []
