"""Canonical download, media, and transcode folder layout."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from core.settings import Settings, settings as default_settings


@dataclass(frozen=True)
class DownloadCategory:
    """Downloader category name plus the library folder it feeds."""

    name: str
    library: str
    arr_app: str


DOWNLOAD_CATEGORIES: tuple[DownloadCategory, ...] = (
    DownloadCategory("sonarr", "tv", "sonarr"),
    DownloadCategory("radarr", "movies", "radarr"),
    DownloadCategory("anime", "anime", "sonarr"),
    DownloadCategory("lidarr", "music", "lidarr"),
)

LIBRARY_FOLDERS: tuple[str, ...] = ("tv", "movies", "anime", "music", "books", "comics")


@dataclass(frozen=True)
class LibraryLayout:
    media_dir: Path
    download_dir: Path
    cache_dir: Path

    @classmethod
    def from_settings(cls, app_settings: Settings | None = None) -> "LibraryLayout":
        cfg = app_settings or default_settings
        return cls(
            media_dir=Path(cfg.media_dir),
            download_dir=Path(cfg.download_dir),
            cache_dir=Path(cfg.cache_dir),
        )

    @property
    def complete(self) -> Path:
        return self.download_dir / "complete"

    @property
    def incomplete(self) -> Path:
        return self.download_dir / "incomplete"

    @property
    def torrents(self) -> Path:
        return self.download_dir / "torrents"

    @property
    def tv(self) -> Path:
        return self.media_dir / "tv"

    @property
    def movies(self) -> Path:
        return self.media_dir / "movies"

    @property
    def anime(self) -> Path:
        return self.media_dir / "anime"

    @property
    def music(self) -> Path:
        return self.media_dir / "music"

    @property
    def books(self) -> Path:
        return self.media_dir / "books"

    @property
    def bookdrop(self) -> Path:
        return self.books / "bookdrop"

    @property
    def comics(self) -> Path:
        return self.media_dir / "comics"

    @property
    def transcode(self) -> Path:
        return self.cache_dir / "transcode"

    @property
    def transcode_jellyfin(self) -> Path:
        return self.transcode / "jellyfin"

    @property
    def transcode_plex(self) -> Path:
        return self.transcode / "plex"

    def media_path(self, library: str) -> Path:
        return self.media_dir / library

    def complete_path(self, library: str) -> Path:
        return self.complete / library

    def torrent_path(self, library: str) -> Path:
        return self.torrents / library

    def directories(self) -> list[Path]:
        dirs: list[Path] = [
            self.complete,
            self.incomplete,
            self.torrents,
            self.transcode,
            self.transcode_jellyfin,
            self.transcode_plex,
        ]
        for name in LIBRARY_FOLDERS:
            dirs.append(self.media_path(name))
            dirs.append(self.complete_path(name))
            dirs.append(self.torrent_path(name))
        dirs.append(self.bookdrop)
        return dirs

    def as_dict(self) -> dict[str, str | dict[str, str]]:
        libraries = {name: str(self.media_path(name)) for name in LIBRARY_FOLDERS}
        complete = {name: str(self.complete_path(name)) for name in LIBRARY_FOLDERS}
        torrents = {name: str(self.torrent_path(name)) for name in LIBRARY_FOLDERS}
        return {
            "media": str(self.media_dir),
            "downloads": str(self.download_dir),
            "complete": str(self.complete),
            "incomplete": str(self.incomplete),
            "torrents": str(self.torrents),
            "transcode_jellyfin": str(self.transcode_jellyfin),
            "transcode_plex": str(self.transcode_plex),
            "libraries": libraries,
            "complete_categories": complete,
            "torrent_categories": torrents,
        }


def arr_root_folders(layout: LibraryLayout) -> dict[str, Sequence[Path]]:
    """Root folders to register on each *Arr application."""
    return {
        "sonarr": (layout.tv, layout.anime),
        "radarr": (layout.movies,),
        "lidarr": (layout.music,),
    }


def jellyfin_libraries(layout: LibraryLayout) -> tuple[tuple[str, str, Path], ...]:
    """(display name, Jellyfin collectionType, path)."""
    return (
        ("TV", "tvshows", layout.tv),
        ("Movies", "movies", layout.movies),
        ("Anime", "tvshows", layout.anime),
        ("Music", "music", layout.music),
        ("Books", "books", layout.books),
    )
