"""Canonical library folder layout."""

from pathlib import Path

from core.library_layout import LIBRARY_FOLDERS, LibraryLayout
from core.settings import Settings
from core.storage import StorageManager


def test_storage_creates_media_download_and_transcode_folders(tmp_path: Path):
    cfg = Settings(
        config_dir=tmp_path / "config",
        install_dir=tmp_path / "apps",
        download_dir=tmp_path / "downloads",
        media_dir=tmp_path / "media",
        cache_dir=tmp_path / "cache",
    )
    layout = StorageManager(cfg).create_standard_layout()
    assert layout.incomplete.is_dir()
    assert layout.complete.is_dir()
    assert layout.transcode_jellyfin.is_dir()
    assert layout.transcode_plex.is_dir()
    assert layout.bookdrop.is_dir()
    for name in LIBRARY_FOLDERS:
        assert layout.media_path(name).is_dir()
        assert layout.complete_path(name).is_dir()
        assert layout.torrent_path(name).is_dir()


def test_library_layout_paths_are_under_configured_roots(tmp_path: Path):
    cfg = Settings(
        config_dir=tmp_path / "config",
        download_dir=tmp_path / "dl",
        media_dir=tmp_path / "lib",
        cache_dir=tmp_path / "c",
    )
    layout = LibraryLayout.from_settings(cfg)
    payload = layout.as_dict()
    assert payload["libraries"]["anime"] == str(tmp_path / "lib" / "anime")
    assert payload["complete_categories"]["music"] == str(tmp_path / "dl" / "complete" / "music")
    assert layout.bookdrop == tmp_path / "lib" / "books" / "bookdrop"
    assert layout.books == tmp_path / "lib" / "books"
    assert payload["transcode_jellyfin"].endswith("transcode/jellyfin")


def test_jellyfin_libraries_include_books(tmp_path: Path):
    from core.library_layout import jellyfin_libraries

    layout = LibraryLayout(
        media_dir=tmp_path / "lib",
        download_dir=tmp_path / "dl",
        cache_dir=tmp_path / "c",
    )
    names = {row[0]: row[2] for row in jellyfin_libraries(layout)}
    assert names["Books"] == layout.books
