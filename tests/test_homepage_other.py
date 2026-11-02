"""Home's Other downloads: films and series stay out, the rest gets an icon."""

from types import SimpleNamespace
from unittest.mock import patch

from core import homepage_other
from core.homepage_other import download_kind


def test_films_and_series_stay_out():
    assert download_kind("Anything", "sonarr") is None
    assert download_kind("Anything", "radarr") is None
    assert download_kind("Anything", "tv-sonarr") is None
    assert download_kind("Anything", "anime") is None
    assert download_kind("Some.Show.S02E05.720p.WEB", "") is None
    assert download_kind("Some.Movie.2023.2160p.BluRay.x265", "*") is None


def test_the_rest_gets_a_kind():
    assert download_kind("Artist - Album (2020)", "lidarr") == "music"
    assert download_kind("Anything", "books") == "book"
    assert download_kind("Artist_-_Album_[FLAC]", "") == "music"
    assert download_kind("Some Audiobook mp3", "") == "book"
    assert download_kind("[Switch NSP] Mario Kart 8 Deluxe", "") == "game"
    assert download_kind("ubuntu-24.04-desktop-amd64.iso", "") == "disc"
    assert download_kind("Tool.v2.1.x64", "") == "app"
    assert download_kind("photos.zip", "") == "archive"
    assert download_kind("holiday.mp4", "") == "video"
    assert download_kind("Something else", "") == "file"


def test_qbittorrent_keeps_finished_ones_and_leaves_out_video():
    rows = [
        {"name": "Show.S01E01.1080p", "category": "", "progress": 0.5, "hash": "a"},
        {"name": "Movie", "category": "radarr", "progress": 1.0, "hash": "b"},
        {"name": "debian.iso", "category": "", "progress": 1.0, "completion_on": 200, "size": 10, "hash": "c"},
        {"name": "Album FLAC", "category": "", "progress": 0.25, "state": "stalledDL", "added_on": 100, "hash": "d"},
    ]
    client = SimpleNamespace(
        base_url="http://qbit/api/v2",
        app_accessible=lambda: True,
        session=SimpleNamespace(get=lambda url, timeout: SimpleNamespace(status_code=200, json=lambda: rows)),
    )
    plugin = SimpleNamespace(port=8080, is_installed=lambda: True)
    catalog = SimpleNamespace(has=lambda name: name == "qbittorrent", get=lambda name: plugin)
    with patch("core.homepage_other.QBittorrentClient", return_value=client), patch(
        "core.homepage_other.ApplicationCatalog", return_value=catalog
    ), patch("core.homepage_other._running_names", return_value={"qbittorrent"}):
        items = homepage_other.homepage_other_downloads()["items"]
    assert [(i["title"], i["kind"], i["done"], i["status"]) for i in items] == [
        ("Album FLAC", "music", False, "Stalled"),
        ("debian.iso", "disc", True, "Completed"),
    ]
    assert items[1]["when"] == 200
