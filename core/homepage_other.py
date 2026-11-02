"""Home's Other downloads widget: what the download clients fetched that is not a film or a series."""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from applications.catalog import ApplicationCatalog
from core.homepage import _QBIT_STATUS, _TIMEOUT, _fetch_json, _pct, _running_names, _source_ready
from core.integrations.credentials import get_application_api_key
from core.integrations.nzbget import NZBGetClient
from core.integrations.qbittorrent import QBittorrentClient
from core.library_layout import DOWNLOAD_CATEGORIES

logger = logging.getLogger(__name__)

LIMIT = 30
MB = 1024 * 1024
# Sonarr's and Radarr's categories: AIO's own, the library folders and their defaults (tv-sonarr, radarr).
VIDEO_CATEGORIES = frozenset(
    {c.name for c in DOWNLOAD_CATEGORIES if c.arr_app in ("sonarr", "radarr")}
    | {"tv", "movies", "tv-sonarr"}
)
CATEGORY_KINDS = {
    "lidarr": "music",
    "music": "music",
    "books": "book",
    "ebooks": "book",
    "audiobooks": "book",
    "readarr": "book",
}


def _words(words: str) -> re.Pattern[str]:
    # Not \b: release names join words with underscores too.
    return re.compile(rf"(?<![a-z0-9])({words})(?![a-z0-9])", re.I)


# ponytail: name heuristics. A film or series without these tags, in no Sonarr/Radarr category, shows as a video here.
RELEASE_TAGS = _words(r"s\d{1,2}e\d{1,3}|\d{3,4}p|bluray|web-?dl|webrip|hdtv|x26[45]|h\.?26[45]|hevc")
NAME_KINDS = (
    ("book", _words(r"epub|mobi|azw3|pdf|cbz|cbr|m4b|ebook|audiobook")),
    ("music", _words(r"flac|mp3|aac|alac|m4a|ogg|opus|wav|320kbps|discography")),
    ("game", _words(r"nsp|nsz|xci|switch|nintendo|wii|3ds|nds|gba|ps[1-5]|psp|xbox|fitgirl|dodi|gog")),
    ("disc", _words(r"iso|img|dmg")),
    ("app", _words(r"exe|msi|apk|pkg|deb|rpm|appimage|x64|x86|amd64|arm64")),
    ("archive", _words(r"zip|rar|7z|tar|gz")),
    ("video", _words(r"mkv|mp4|avi|mov|webm")),
)


def download_kind(title: str, category: str = "") -> str | None:
    """The icon a download gets, or None for a film or a series."""
    cat = (category or "").strip().lower()
    if cat in VIDEO_CATEGORIES:
        return None
    if cat in CATEGORY_KINDS:
        return CATEGORY_KINDS[cat]
    if RELEASE_TAGS.search(title or ""):
        return None
    return next((kind for kind, pattern in NAME_KINDS if pattern.search(title or "")), "file")


def _item(source: str, item_id: Any, title: str, kind: str, size: float, progress: int, done: bool, when: Any, status: str) -> dict[str, Any]:
    try:
        stamp = max(0, int(float(when or 0)))
    except (TypeError, ValueError):
        stamp = 0
    return {
        "source": source,
        "id": str(item_id or title),
        "title": title,
        "kind": kind,
        "size": int(size or 0),
        "progress": 100 if done else progress,
        "done": done,
        "when": stamp,
        "status": status,
    }


def _rows(data: Any, key: str) -> list[dict[str, Any]]:
    block = data.get(key) if isinstance(data, dict) else None
    slots = block.get("slots") if isinstance(block, dict) else None
    return [row for row in slots if isinstance(row, dict)] if isinstance(slots, list) else []


def _sabnzbd(catalog: ApplicationCatalog, running: set[str]) -> list[dict[str, Any]]:
    if not _source_ready(catalog, running, "sabnzbd", "other", [], need_key=True):
        return []
    plugin = catalog.get("sabnzbd")
    url = f"http://127.0.0.1:{plugin.port}/api"
    key = get_application_api_key("sabnzbd", plugin.config_dir) or ""
    queue, _ = _fetch_json(url, params={"mode": "queue", "output": "json", "apikey": key})
    history, _ = _fetch_json(url, params={"mode": "history", "output": "json", "apikey": key, "limit": 100})
    out: list[dict[str, Any]] = []
    for row in _rows(queue, "queue"):
        title = str(row.get("filename") or "Download")
        kind = download_kind(title, str(row.get("cat") or ""))
        if kind:
            mb = float(row.get("mb") or 0)
            out.append(_item("sabnzbd", row.get("nzo_id"), title, kind, mb * MB, _pct(row.get("percentage")), False, 0, str(row.get("status") or "")))
    for row in _rows(history, "history"):
        if str(row.get("status") or "") != "Completed":
            continue
        title = str(row.get("name") or "Download")
        kind = download_kind(title, str(row.get("category") or ""))
        if kind:
            out.append(_item("sabnzbd", row.get("nzo_id"), title, kind, float(row.get("bytes") or 0), 100, True, row.get("completed"), "Completed"))
    return out


def _nzbget(catalog: ApplicationCatalog, running: set[str]) -> list[dict[str, Any]]:
    if not _source_ready(catalog, running, "nzbget", "other", []):
        return []
    client = NZBGetClient(port=catalog.get("nzbget").port)
    out: list[dict[str, Any]] = []
    for row in client._call("listgroups") or []:
        if not isinstance(row, dict):
            continue
        title = str(row.get("NZBName") or "Download")
        kind = download_kind(title, str(row.get("Category") or ""))
        if kind:
            total = float(row.get("FileSizeMB") or 0)
            left = float(row.get("RemainingSizeMB") or 0)
            progress = _pct(100 * (1 - left / total)) if total else 0
            out.append(_item("nzbget", row.get("NZBID"), title, kind, total * MB, progress, False, 0, str(row.get("Status") or "")))
    # ponytail: NZBGet sends its whole history; fine at Home's once-a-minute poll, page it if that ever gets heavy.
    for row in client._call("history") or []:
        if not isinstance(row, dict) or not str(row.get("Status") or "").startswith("SUCCESS"):
            continue
        title = str(row.get("Name") or row.get("NZBName") or "Download")
        kind = download_kind(title, str(row.get("Category") or ""))
        if kind:
            out.append(_item("nzbget", row.get("NZBID") or row.get("ID"), title, kind, float(row.get("FileSizeMB") or 0) * MB, 100, True, row.get("HistoryTime"), "Completed"))
    return out


def _qbittorrent(catalog: ApplicationCatalog, running: set[str]) -> list[dict[str, Any]]:
    if not _source_ready(catalog, running, "qbittorrent", "other", []):
        return []
    client = QBittorrentClient(port=catalog.get("qbittorrent").port)
    if not (client.app_accessible() or client.login()):
        return []
    resp = client.session.get(f"{client.base_url}/torrents/info", timeout=_TIMEOUT)
    rows = resp.json() if resp.status_code == 200 else []
    out: list[dict[str, Any]] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        title = str(row.get("name") or "Torrent")
        kind = download_kind(title, str(row.get("category") or ""))
        if not kind:
            continue
        done = float(row.get("progress") or 0) >= 1
        finished = row.get("completion_on") if done and int(row.get("completion_on") or 0) > 0 else None
        out.append(
            _item(
                "qbittorrent",
                row.get("hash"),
                title,
                kind,
                float(row.get("size") or 0),
                int(float(row.get("progress") or 0) * 100),
                done,
                finished or row.get("added_on"),
                "Completed" if done else _QBIT_STATUS.get(str(row.get("state") or ""), str(row.get("state") or "")),
            )
        )
    return out


def _safely(collect: Callable[[ApplicationCatalog, set[str]], list[dict[str, Any]]], catalog: ApplicationCatalog, running: set[str]) -> list[dict[str, Any]]:
    try:
        return collect(catalog, running)
    except Exception as exc:
        logger.debug("Other downloads from %s failed: %s", collect.__name__, exc)
        return []


def homepage_other_downloads() -> dict[str, Any]:
    """Still downloading first, then finished, newest first."""
    catalog = ApplicationCatalog()
    running = _running_names()
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(_safely, collect, catalog, running) for collect in (_sabnzbd, _nzbget, _qbittorrent)]
        items = [item for future in futures for item in future.result()]
    items.sort(key=lambda item: (item["done"], -item["when"]))
    return {"items": items[:LIMIT]}
