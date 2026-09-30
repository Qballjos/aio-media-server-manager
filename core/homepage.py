"""Household homepage snapshot: launcher plus widgets from installed app APIs."""

from __future__ import annotations

import copy
import logging
import threading
import time
from calendar import monthrange
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from typing import Any, Optional
from urllib.parse import quote

import requests

from applications.catalog import ApplicationCatalog
from core.integrations.credentials import get_application_api_key
from core.integrations.jellyfin import jellyfin_auth_headers
from core.integrations.nzbget import NZBGetClient
from core.integrations.plex import PlexClient
from core.integrations.qbittorrent import QBittorrentClient
from core.supervisor import ProcessSupervisor

logger = logging.getLogger(__name__)

_TIMEOUT = 4.0
_CACHE_TTL = 30.0
_LAUNCHER_SKIP = frozenset({"recyclarr", "flaresolverr"})
_LAUNCHER_CATEGORY_ORDER = (
    "media",
    "requests",
    "automation",
    "indexers",
    "downloading",
    "subtitles",
    "optimization",
    "maintenance",
)

_cache_guard = threading.Lock()
_snapshots: dict[str, "_SnapshotEntry"] = {}
_host_build_locks: dict[str, threading.Lock] = {}


class _SnapshotEntry:
    __slots__ = ("snapshot", "built_at", "refreshing")

    def __init__(self, snapshot: dict[str, Any], built_at: float) -> None:
        self.snapshot = snapshot
        self.built_at = built_at
        self.refreshing = False


def month_calendar_span(today: date | None = None) -> tuple[date, date]:
    """Monday–Sunday grid covering the current month (including leading/trailing days)."""
    today = today or date.today()
    first = today.replace(day=1)
    start = first - timedelta(days=first.weekday())
    last = today.replace(day=monthrange(today.year, today.month)[1])
    end = last + timedelta(days=(6 - last.weekday()))
    return start, end


def _shift_month(value: date, delta: int) -> date:
    month = value.month - 1 + delta
    year = value.year + month // 12
    month = month % 12 + 1
    return date(year, month, 1)


def calendar_fetch_span(today: date | None = None) -> tuple[date, date]:
    """Previous month through next month, Monday–Sunday, so week/month paging has events."""
    today = today or date.today()
    first = _shift_month(today, -1)
    start = first - timedelta(days=first.weekday())
    last = _shift_month(today, 2) - timedelta(days=1)
    end = last + timedelta(days=(6 - last.weekday()))
    return start, end


def clear_homepage_snapshot_cache() -> None:
    """Drop cached Home widgets (tests, and after a Seerr request)."""
    with _cache_guard:
        _snapshots.clear()


def homepage_snapshot(host: str, *, force: bool = False) -> dict[str, Any]:
    ident = (host or "127.0.0.1").strip() or "127.0.0.1"
    if force:
        with _lock_for(ident):
            return _build_and_store(ident)

    cached = _cached_copy(ident)
    if cached is not None:
        snap, age = cached
        if age < _CACHE_TTL:
            return snap
        _schedule_refresh(ident)
        return snap

    with _lock_for(ident):
        cached = _cached_copy(ident)
        if cached is not None:
            snap, age = cached
            if age >= _CACHE_TTL:
                _schedule_refresh(ident)
            return snap
        return _build_and_store(ident)


def _lock_for(host: str) -> threading.Lock:
    with _cache_guard:
        lock = _host_build_locks.get(host)
        if lock is None:
            lock = threading.Lock()
            _host_build_locks[host] = lock
        return lock


def _cached_copy(host: str) -> tuple[dict[str, Any], float] | None:
    with _cache_guard:
        entry = _snapshots.get(host)
        if entry is None:
            return None
        age = time.monotonic() - entry.built_at
        return copy.deepcopy(entry.snapshot), age


def _schedule_refresh(host: str) -> None:
    with _cache_guard:
        entry = _snapshots.get(host)
        if entry is None or entry.refreshing:
            return
        entry.refreshing = True
    threading.Thread(
        target=_refresh_snapshot,
        args=(host,),
        name=f"homepage-refresh-{host}",
        daemon=True,
    ).start()


def _refresh_snapshot(host: str) -> None:
    try:
        with _lock_for(host):
            _build_and_store(host)
    except Exception as exc:
        logger.debug("Homepage background refresh failed: %s", exc)
        with _cache_guard:
            entry = _snapshots.get(host)
            if entry is not None:
                entry.refreshing = False


def _build_and_store(host: str) -> dict[str, Any]:
    snapshot = _build_homepage_snapshot(host)
    with _cache_guard:
        _snapshots[host] = _SnapshotEntry(snapshot, time.monotonic())
    return copy.deepcopy(snapshot)


def _build_homepage_snapshot(host: str) -> dict[str, Any]:
    catalog = ApplicationCatalog()
    running = _running_names()
    start, end = calendar_fetch_span()
    notes: list[dict[str, Any]] = []

    apps = _launcher_apps(catalog, running, host)

    calendar: list[dict[str, Any]] = []
    downloads: list[dict[str, Any]] = []
    recent: list[dict[str, Any]] = []
    requests_row: list[dict[str, Any]] = []

    sonarr_notes: list[dict[str, Any]] = []
    radarr_notes: list[dict[str, Any]] = []
    sab_notes: list[dict[str, Any]] = []
    nzb_notes: list[dict[str, Any]] = []
    qbit_notes: list[dict[str, Any]] = []
    jelly_notes: list[dict[str, Any]] = []
    plex_notes: list[dict[str, Any]] = []
    seerr_notes: list[dict[str, Any]] = []

    with ThreadPoolExecutor(max_workers=8) as pool:
        fut_sonarr = pool.submit(_collect_sonarr_calendar, catalog, running, start, end, sonarr_notes)
        fut_radarr = pool.submit(_collect_radarr_calendar, catalog, running, start, end, radarr_notes)
        fut_sab = pool.submit(_collect_sabnzbd_queue, catalog, running, sab_notes)
        fut_nzb = pool.submit(_collect_nzbget_queue, catalog, running, nzb_notes)
        fut_qbit = pool.submit(_collect_qbittorrent_queue, catalog, running, qbit_notes)
        fut_jelly = pool.submit(_collect_jellyfin_recent, catalog, running, jelly_notes, host)
        fut_plex = pool.submit(_collect_plex_recent, catalog, running, plex_notes, host)
        fut_seerr = pool.submit(_collect_seerr_requests, catalog, running, seerr_notes, host)
        calendar.extend(fut_sonarr.result())
        calendar.extend(fut_radarr.result())
        downloads.extend(fut_sab.result())
        downloads.extend(fut_nzb.result())
        downloads.extend(fut_qbit.result())
        recent.extend(fut_jelly.result())
        recent.extend(fut_plex.result())
        requests_row.extend(fut_seerr.result())

    calendar.sort(key=lambda item: (item.get("when") or "", item.get("title") or ""))
    recent.sort(key=_when_sort_key, reverse=True)
    notes.extend(sonarr_notes)
    notes.extend(radarr_notes)
    notes.extend(sab_notes)
    notes.extend(nzb_notes)
    notes.extend(qbit_notes)
    notes.extend(jelly_notes)
    notes.extend(plex_notes)
    notes.extend(seerr_notes)

    seerr = catalog.has("seerr") and catalog.get("seerr").is_installed()
    seerr_running = seerr and "seerr" in running
    if not seerr:
        _note(notes, "search", "seerr", "skipped", "not installed")
    elif not seerr_running:
        _note(notes, "search", "seerr", "skipped", "stopped")
    else:
        key = get_application_api_key("seerr", catalog.get("seerr").config_dir)
        if key:
            _note(notes, "search", "seerr", "ok", "ready for search and requests")
        else:
            _note(notes, "search", "seerr", "error", "running but no API key yet")

    return {
        "apps": apps,
        "calendar": calendar[:400],
        "downloads": downloads[:40],
        "recent": recent[:24],
        "requests": requests_row[:16],
        "seerr": {
            "available": bool(seerr_running),
            "url": _web_url(host, _port(catalog, "seerr", 5055)) if seerr else None,
        },
        "widgets": notes,
    }


def homepage_search(host: str, query: str) -> dict[str, Any]:
    catalog = ApplicationCatalog()
    running = _running_names()
    term = (query or "").strip()
    if len(term) < 2:
        return {"query": term, "results": [], "seerr": False, "error": None}
    seerr_error: str | None = None
    if catalog.has("seerr") and catalog.get("seerr").is_installed() and "seerr" in running:
        results, seerr_error = _seerr_search(catalog, term)
        if not seerr_error:
            return {"query": term, "results": results, "seerr": True, "error": None}
    results = []
    if catalog.has("sonarr") and catalog.get("sonarr").is_installed() and "sonarr" in running:
        results.extend(_sonarr_lookup(catalog, term))
    if catalog.has("radarr") and catalog.get("radarr").is_installed() and "radarr" in running:
        results.extend(_radarr_lookup(catalog, term))
    error = f"Seerr search failed ({seerr_error})" if seerr_error else None
    if not results and not seerr_error and not any(
        catalog.has(name) and catalog.get(name).is_installed() and name in running
        for name in ("seerr", "sonarr", "radarr")
    ):
        error = "Start Seerr, Sonarr or Radarr to search."
    return {"query": term, "results": results[:20], "seerr": False, "error": error}


def homepage_request(payload: dict[str, Any]) -> dict[str, Any]:
    catalog = ApplicationCatalog()
    running = _running_names()
    if not (catalog.has("seerr") and catalog.get("seerr").is_installed() and "seerr" in running):
        return {"ok": False, "detail": "Seerr is not installed or not running."}
    media_type = str(payload.get("mediaType") or payload.get("media_type") or "").strip().lower()
    if media_type in {"series", "show", "tv"}:
        media_type = "tv"
    if media_type not in {"movie", "tv"}:
        return {"ok": False, "detail": "mediaType must be movie or tv."}
    media_id = payload.get("mediaId") or payload.get("tmdbId") or payload.get("id")
    try:
        media_id = int(media_id)
    except (TypeError, ValueError):
        return {"ok": False, "detail": "mediaId is required."}
    body: dict[str, Any] = {"mediaId": media_id, "mediaType": media_type}
    seasons = payload.get("seasons")
    if media_type == "tv":
        body["seasons"] = seasons if seasons is not None else "all"
    plugin = catalog.get("seerr")
    key = get_application_api_key("seerr", plugin.config_dir)
    headers = {"Content-Type": "application/json"}
    if key:
        headers["X-Api-Key"] = key
    try:
        resp = requests.post(
            f"http://127.0.0.1:{plugin.port}/api/v1/request",
            headers=headers,
            json=body,
            timeout=_TIMEOUT,
        )
        if resp.status_code in (200, 201):
            clear_homepage_snapshot_cache()
            return {"ok": True, "detail": "Request submitted."}
        return {"ok": False, "detail": f"Seerr returned HTTP {resp.status_code}."}
    except Exception as exc:
        logger.debug("Seerr request failed: %s", exc)
        return {"ok": False, "detail": "Could not reach Seerr."}


def _running_names() -> set[str]:
    try:
        supervisor = ProcessSupervisor.get()
        return {item["name"] for item in supervisor.list_processes() if item.get("state") == "running"}
    except Exception:
        return set()


def _launcher_apps(catalog: ApplicationCatalog, running: set[str], host: str) -> list[dict[str, Any]]:
    apps: list[dict[str, Any]] = []
    for plugin in catalog.all_plugins():
        if plugin.name in _LAUNCHER_SKIP or not plugin.manifest.daemon:
            continue
        if not plugin.is_installed():
            continue
        apps.append(
            {
                "name": plugin.name,
                "display_name": plugin.manifest.display_name,
                "category": plugin.manifest.category.value,
                "port": plugin.port,
                "running": plugin.name in running,
                "url": _web_url(host, plugin.port),
            }
        )
    order = {name: index for index, name in enumerate(_LAUNCHER_CATEGORY_ORDER)}
    apps.sort(
        key=lambda item: (
            order.get(item["category"], len(order)),
            item["display_name"].lower(),
        )
    )
    return apps


def _web_url(host: str, port: int) -> str:
    safe_host = (host or "127.0.0.1").split(":")[0] or "127.0.0.1"
    return f"http://{safe_host}:{port}"


def _port(catalog: ApplicationCatalog, name: str, fallback: int) -> int:
    if catalog.has(name):
        return catalog.get(name).port
    return fallback


def _arr_headers(name: str, config_dir) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    key = get_application_api_key(name, config_dir)
    if key:
        headers["X-Api-Key"] = key
    return headers


def _note(
    notes: list[dict[str, Any]],
    widget: str,
    source: str,
    state: str,
    detail: str,
    *,
    count: int = 0,
) -> None:
    notes.append(
        {
            "widget": widget,
            "source": source,
            "state": state,
            "detail": detail,
            "count": count,
        }
    )


def _source_ready(
    catalog: ApplicationCatalog,
    running: set[str],
    name: str,
    widget: str,
    notes: list[dict[str, Any]],
    *,
    need_key: bool = False,
) -> bool:
    if not catalog.has(name) or not catalog.get(name).is_installed():
        _note(notes, widget, name, "skipped", "not installed")
        return False
    if name not in running:
        _note(notes, widget, name, "skipped", "stopped")
        return False
    if need_key and not get_application_api_key(name, catalog.get(name).config_dir):
        _note(notes, widget, name, "error", "running but no API key yet")
        return False
    return True


def _iso_when(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return text


def _when_sort_key(item: dict[str, Any]) -> float:
    text = str(item.get("when") or "").strip()
    if not text:
        return 0.0
    if text.isdigit() and len(text) >= 9:
        try:
            return float(text)
        except ValueError:
            return 0.0
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _get_json(url: str, *, headers: Optional[dict[str, str]] = None, params: Optional[dict[str, Any]] = None) -> Any:
    data, _error = _fetch_json(url, headers=headers, params=params)
    return data


def _fetch_json(
    url: str,
    *,
    headers: Optional[dict[str, str]] = None,
    params: Optional[dict[str, Any]] = None,
    timeout: float | None = None,
) -> tuple[Any, str | None]:
    try:
        resp = requests.get(url, headers=headers or {}, params=params, timeout=timeout or _TIMEOUT)
        if resp.status_code == 200:
            return resp.json(), None
        return None, f"HTTP {resp.status_code}"
    except requests.Timeout:
        return None, f"timed out after {int(timeout or _TIMEOUT)}s"
    except Exception as exc:
        logger.debug("Homepage GET %s failed: %s", url, exc)
        return None, str(exc)[:180]


def _fetch_bytes(
    url: str,
    *,
    headers: Optional[dict[str, str]] = None,
    params: Optional[dict[str, Any]] = None,
) -> tuple[bytes | None, str, str | None]:
    try:
        resp = requests.get(url, headers=headers or {}, params=params, timeout=_TIMEOUT)
        if resp.status_code != 200 or not resp.content:
            return None, "", f"HTTP {resp.status_code}"
        ctype = (resp.headers.get("Content-Type") or "image/jpeg").split(";")[0].strip()
        return resp.content, ctype or "image/jpeg", None
    except Exception as exc:
        logger.debug("Homepage image GET %s failed: %s", url, exc)
        return None, "", str(exc)[:180]


def homepage_art(source: str, item_id: str) -> tuple[bytes | None, str]:
    """Artwork for Home poster rails. Authenticated via the manager session."""
    catalog = ApplicationCatalog()
    running = _running_names()
    ident = (item_id or "").strip()
    if not ident:
        return None, ""
    if source == "jellyfin" and catalog.has("jellyfin") and "jellyfin" in running:
        plugin = catalog.get("jellyfin")
        key = get_application_api_key("jellyfin", plugin.config_dir)
        body, ctype, _err = _fetch_bytes(
            f"http://127.0.0.1:{plugin.port}/Items/{quote(ident, safe='')}/Images/Primary",
            headers=jellyfin_auth_headers(key),
            params={"fillWidth": "240", "fillHeight": "360", "quality": "80"},
        )
        return body, ctype
    if source == "plex" and catalog.has("plex") and "plex" in running:
        plugin = catalog.get("plex")
        client = PlexClient(port=plugin.port, config_dir=plugin.config_dir)
        body, ctype, _err = _fetch_bytes(
            f"{client.base_url}/library/metadata/{quote(ident, safe='')}/thumb",
            headers=client._headers(),
            params={"width": "240", "height": "360"},
        )
        return body, ctype
    return None, ""


def _finish_source(
    notes: list[dict[str, Any]],
    widget: str,
    source: str,
    items: list[dict[str, Any]],
    error: str | None,
    empty_detail: str,
) -> list[dict[str, Any]]:
    if error:
        _note(notes, widget, source, "error", error)
        return []
    if not items:
        _note(notes, widget, source, "empty", empty_detail)
        return []
    _note(notes, widget, source, "ok", f"{len(items)} item(s)", count=len(items))
    return items


def _collect_sonarr_calendar(
    catalog: ApplicationCatalog,
    running: set[str],
    start: date,
    end: date,
    notes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not _source_ready(catalog, running, "sonarr", "calendar", notes, need_key=True):
        return []
    plugin = catalog.get("sonarr")
    data, error = _fetch_json(
        f"http://127.0.0.1:{plugin.port}/api/v3/calendar",
        headers=_arr_headers("sonarr", plugin.config_dir),
        params={
            "start": start.isoformat(),
            "end": end.isoformat(),
            "unmonitored": "false",
            "includeSeries": "true",
        },
    )
    return _finish_source(
        notes,
        "calendar",
        "sonarr",
        _parse_sonarr_calendar(data),
        error or (None if isinstance(data, list) else "unexpected calendar payload"),
        "calendar is empty in this window",
    )


def _parse_sonarr_calendar(data: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if not isinstance(data, list):
        return items
    for row in data:
        if not isinstance(row, dict):
            continue
        series = row.get("series") if isinstance(row.get("series"), dict) else {}
        title = series.get("title") or row.get("title") or "Episode"
        season = row.get("seasonNumber")
        episode = row.get("episodeNumber")
        ep = f"S{int(season):02d}E{int(episode):02d}" if season is not None and episode is not None else ""
        items.append(
            {
                "source": "sonarr",
                "kind": "episode",
                "title": title,
                "detail": " ".join(part for part in (ep, row.get("title") or "") if part),
                "when": _iso_when(row.get("airDateUtc") or row.get("airDate")),
                "has_file": bool(row.get("hasFile")),
            }
        )
    return items


def _collect_radarr_calendar(
    catalog: ApplicationCatalog,
    running: set[str],
    start: date,
    end: date,
    notes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not _source_ready(catalog, running, "radarr", "calendar", notes, need_key=True):
        return []
    plugin = catalog.get("radarr")
    data, error = _fetch_json(
        f"http://127.0.0.1:{plugin.port}/api/v3/calendar",
        headers=_arr_headers("radarr", plugin.config_dir),
        params={"start": start.isoformat(), "end": end.isoformat(), "unmonitored": "false"},
    )
    return _finish_source(
        notes,
        "calendar",
        "radarr",
        _parse_radarr_calendar(data),
        error or (None if isinstance(data, list) else "unexpected calendar payload"),
        "calendar is empty in this window",
    )


def _parse_radarr_calendar(data: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if not isinstance(data, list):
        return items
    for row in data:
        if not isinstance(row, dict):
            continue
        when = row.get("digitalRelease") or row.get("physicalRelease") or row.get("inCinemas") or ""
        items.append(
            {
                "source": "radarr",
                "kind": "movie",
                "title": row.get("title") or "Movie",
                "detail": str(row.get("year") or ""),
                "when": _iso_when(when),
                "has_file": bool(row.get("hasFile")),
            }
        )
    return items


def _collect_sabnzbd_queue(
    catalog: ApplicationCatalog,
    running: set[str],
    notes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not _source_ready(catalog, running, "sabnzbd", "downloads", notes, need_key=True):
        return []
    plugin = catalog.get("sabnzbd")
    key = get_application_api_key("sabnzbd", plugin.config_dir) or ""
    data, error = _fetch_json(
        f"http://127.0.0.1:{plugin.port}/api",
        params={"mode": "queue", "output": "json", "apikey": key},
    )
    queue = data.get("queue") if isinstance(data, dict) else None
    slots = queue.get("slots") if isinstance(queue, dict) else None
    items: list[dict[str, Any]] = []
    if isinstance(slots, list):
        for row in slots:
            if not isinstance(row, dict):
                continue
            items.append(
                {
                    "source": "sabnzbd",
                    "title": row.get("filename") or row.get("name") or "Download",
                    "status": row.get("status") or "",
                    "progress": _pct(row.get("percentage")),
                }
            )
    payload_error = None if isinstance(data, dict) else "unexpected queue payload"
    return _finish_source(
        notes,
        "downloads",
        "sabnzbd",
        items,
        error or payload_error,
        "queue is empty",
    )


def _collect_nzbget_queue(
    catalog: ApplicationCatalog,
    running: set[str],
    notes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not _source_ready(catalog, running, "nzbget", "downloads", notes):
        return []
    plugin = catalog.get("nzbget")
    try:
        groups = NZBGetClient(port=plugin.port)._call("listgroups")
        error = None
    except Exception as exc:
        logger.debug("NZBGet queue failed: %s", exc)
        groups = None
        error = str(exc)[:180]
    items: list[dict[str, Any]] = []
    if isinstance(groups, list):
        for row in groups:
            if not isinstance(row, dict):
                continue
            remaining = float(row.get("RemainingSizeMB") or 0)
            total = float(row.get("FileSizeMB") or 0) or 1.0
            items.append(
                {
                    "source": "nzbget",
                    "title": row.get("NZBName") or "Download",
                    "status": row.get("Status") or "",
                    "progress": max(0, min(100, int(round(100 * (1.0 - remaining / total))))),
                }
            )
    elif groups is None and not error:
        error = "could not read NZBGet queue"
    return _finish_source(notes, "downloads", "nzbget", items, error, "queue is empty")


def _collect_qbittorrent_queue(
    catalog: ApplicationCatalog,
    running: set[str],
    notes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not _source_ready(catalog, running, "qbittorrent", "downloads", notes):
        return []
    plugin = catalog.get("qbittorrent")
    client = QBittorrentClient(port=plugin.port)
    if not (client.app_accessible() or client.login()):
        return _finish_source(notes, "downloads", "qbittorrent", [], "WebUI login failed", "queue is empty")
    try:
        resp = client.session.get(f"{client.base_url}/torrents/info", timeout=_TIMEOUT)
        if resp.status_code != 200:
            return _finish_source(
                notes, "downloads", "qbittorrent", [], f"HTTP {resp.status_code}", "queue is empty"
            )
        rows = resp.json()
    except Exception as exc:
        logger.debug("qBittorrent torrents failed: %s", exc)
        return _finish_source(notes, "downloads", "qbittorrent", [], str(exc)[:180], "queue is empty")
    items: list[dict[str, Any]] = []
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            state = str(row.get("state") or "")
            if state in {"pausedUP", "stalledUP", "uploading", "queuedUP"} and float(row.get("progress") or 0) >= 1:
                continue
            items.append(
                {
                    "source": "qbittorrent",
                    "title": row.get("name") or "Torrent",
                    "status": state,
                    "progress": int(round(float(row.get("progress") or 0) * 100)),
                }
            )
    error = None if isinstance(rows, list) else "unexpected torrents payload"
    return _finish_source(notes, "downloads", "qbittorrent", items, error, "no active torrents")


def _collect_jellyfin_recent(
    catalog: ApplicationCatalog,
    running: set[str],
    notes: list[dict[str, Any]],
    host: str,
) -> list[dict[str, Any]]:
    if not _source_ready(catalog, running, "jellyfin", "recent", notes, need_key=True):
        return []
    plugin = catalog.get("jellyfin")
    key = get_application_api_key("jellyfin", plugin.config_dir)
    data, error = _fetch_json(
        f"http://127.0.0.1:{plugin.port}/Items",
        headers=jellyfin_auth_headers(key),
        params={
            "Recursive": "true",
            "SortBy": "DateCreated",
            "SortOrder": "Descending",
            "IncludeItemTypes": "Movie,Episode",
            "Limit": "20",
            "Fields": "DateCreated,PrimaryImageAspectRatio,SeriesName",
        },
    )
    rows = data.get("Items") if isinstance(data, dict) else None
    items: list[dict[str, Any]] = []
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            kind = str(row.get("Type") or "")
            item_id = str(row.get("Id") or "")
            poster_id = str(row.get("SeriesId") or item_id) if kind == "Episode" else item_id
            if kind == "Episode":
                season = row.get("ParentIndexNumber")
                episode = row.get("IndexNumber")
                ep = (
                    f"S{int(season):02d}E{int(episode):02d}"
                    if season is not None and episode is not None
                    else ""
                )
                title = row.get("SeriesName") or row.get("Name") or "Episode"
                detail = " ".join(part for part in (ep, row.get("Name") or "") if part)
            else:
                title = row.get("Name") or "Movie"
                detail = str(row.get("ProductionYear") or "Movie")
            items.append(
                {
                    "source": "jellyfin",
                    "title": title,
                    "detail": detail,
                    "when": str(row.get("DateCreated") or "")[:16],
                    "poster": f"/api/homepage/art?source=jellyfin&item_id={quote(poster_id, safe='')}" if poster_id else "",
                    "url": f"{_web_url(host, plugin.port)}/web/#/details?id={quote(item_id, safe='')}" if item_id else "",
                }
            )
    payload_error = None if isinstance(data, dict) else "unexpected items payload"
    if error in ("HTTP 401", "HTTP 403"):
        error = f"{error} — Jellyfin rejected the API key; paste a new one in Settings → Homepage"
    return _finish_source(
        notes,
        "recent",
        "jellyfin",
        items,
        error or payload_error,
        "library returned no recently added items",
    )


def _collect_plex_recent(
    catalog: ApplicationCatalog,
    running: set[str],
    notes: list[dict[str, Any]],
    host: str,
) -> list[dict[str, Any]]:
    if not _source_ready(catalog, running, "plex", "recent", notes):
        return []
    plugin = catalog.get("plex")
    client = PlexClient(port=plugin.port, config_dir=plugin.config_dir)
    try:
        resp = requests.get(
            f"{client.base_url}/library/recentlyAdded",
            headers=client._headers(),
            timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            return _finish_source(notes, "recent", "plex", [], f"HTTP {resp.status_code}", "")
        payload = resp.json()
    except Exception as exc:
        logger.debug("Plex recently added failed: %s", exc)
        return _finish_source(notes, "recent", "plex", [], str(exc)[:180], "")
    container = payload.get("MediaContainer") if isinstance(payload, dict) else None
    rows = container.get("Metadata") if isinstance(container, dict) else None
    items: list[dict[str, Any]] = []
    if isinstance(rows, list):
        for row in rows[:20]:
            if not isinstance(row, dict):
                continue
            kind = str(row.get("type") or "")
            rating_key = str(row.get("grandparentRatingKey") or row.get("ratingKey") or "")
            if kind == "episode":
                title = row.get("grandparentTitle") or row.get("title") or "Episode"
                season = row.get("parentIndex")
                episode = row.get("index")
                ep = (
                    f"S{int(season):02d}E{int(episode):02d}"
                    if season is not None and episode is not None
                    else ""
                )
                detail = " ".join(part for part in (ep, row.get("title") or "") if part)
            else:
                title = row.get("title") or "Item"
                detail = str(row.get("year") or kind)
            item_key = str(row.get("ratingKey") or "")
            items.append(
                {
                    "source": "plex",
                    "title": title,
                    "detail": detail,
                    "when": str(row.get("addedAt") or row.get("originallyAvailableAt") or ""),
                    "poster": f"/api/homepage/art?source=plex&item_id={quote(rating_key, safe='')}" if rating_key else "",
                    "url": f"{_web_url(host, plugin.port)}/web/index.html#!/server/library/metadata/{quote(item_key, safe='')}" if item_key else "",
                }
            )
    error = None if isinstance(payload, dict) else "unexpected recently added payload"
    return _finish_source(
        notes,
        "recent",
        "plex",
        items,
        error,
        "library returned no recently added items",
    )


def _collect_seerr_requests(
    catalog: ApplicationCatalog,
    running: set[str],
    notes: list[dict[str, Any]],
    host: str,
) -> list[dict[str, Any]]:
    if not _source_ready(catalog, running, "seerr", "requests", notes, need_key=True):
        return []
    plugin = catalog.get("seerr")
    key = get_application_api_key("seerr", plugin.config_dir) or ""
    headers = {"Content-Type": "application/json", "X-Api-Key": key}
    data, error = _fetch_json(
        f"http://127.0.0.1:{plugin.port}/api/v1/request",
        headers=headers,
        params={"take": "16", "skip": "0", "filter": "all", "sort": "added"},
    )
    rows = data.get("results") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return _finish_source(
            notes,
            "requests",
            "seerr",
            [],
            error or (None if isinstance(data, dict) else "unexpected request payload"),
            "no requests yet",
        )
    items = _seerr_request_cards(plugin, headers, rows[:16], host)
    return _finish_source(
        notes,
        "requests",
        "seerr",
        items,
        error,
        "no requests yet",
    )


def _seerr_request_cards(
    plugin: Any,
    headers: dict[str, str],
    rows: list[Any],
    host: str,
) -> list[dict[str, Any]]:
    jobs: list[tuple[dict[str, Any], str, int]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        media = row.get("media") if isinstance(row.get("media"), dict) else {}
        media_type = str(media.get("mediaType") or row.get("type") or "movie").lower()
        if media_type in {"tv", "series", "tvshow"}:
            media_type = "tv"
        else:
            media_type = "movie"
        try:
            tmdb_id = int(media.get("tmdbId") or 0)
        except (TypeError, ValueError):
            tmdb_id = 0
        if tmdb_id:
            jobs.append((row, media_type, tmdb_id))

    details: dict[tuple[str, int], dict[str, Any]] = {}
    if jobs:
        with ThreadPoolExecutor(max_workers=6) as pool:
            futs = {
                pool.submit(_seerr_media_details, plugin, headers, media_type, tmdb_id): (media_type, tmdb_id)
                for _row, media_type, tmdb_id in jobs
            }
            for fut in as_completed(futs):
                key = futs[fut]
                try:
                    details[key] = fut.result() or {}
                except Exception:
                    details[key] = {}

    items: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for row, media_type, tmdb_id in jobs:
        ident = (media_type, tmdb_id)
        if ident in seen:
            continue
        seen.add(ident)
        info = details.get(ident) or {}
        who = row.get("requestedBy") if isinstance(row.get("requestedBy"), dict) else {}
        requester = who.get("displayName") or who.get("username") or ""
        title = info.get("title") or f"{media_type} {tmdb_id}"
        path = f"tv/{tmdb_id}" if media_type == "tv" else f"movie/{tmdb_id}"
        items.append(
            {
                "source": "seerr",
                "title": title,
                "detail": requester,
                "poster": info.get("poster") or "",
                "url": f"{_web_url(host, plugin.port)}/{path}",
                "mediaType": media_type,
                "mediaId": tmdb_id,
            }
        )
    return items


def _seerr_media_details(
    plugin: Any,
    headers: dict[str, str],
    media_type: str,
    tmdb_id: int,
) -> dict[str, Any]:
    kind = "tv" if media_type == "tv" else "movie"
    data, _error = _fetch_json(
        f"http://127.0.0.1:{plugin.port}/api/v1/{kind}/{tmdb_id}",
        headers=headers,
        timeout=2.0,
    )
    if not isinstance(data, dict):
        return {}
    poster = data.get("posterPath") or ""
    return {
        "title": data.get("title") or data.get("name") or "",
        "poster": f"https://image.tmdb.org/t/p/w185{poster}" if poster else "",
    }


_SEERR_MEDIA_STATUS = {2: "requested", 3: "requested", 4: "partial", 5: "available"}


def seerr_media_status(row: dict[str, Any]) -> str:
    info = row.get("mediaInfo")
    try:
        code = int(info.get("status")) if isinstance(info, dict) else 0
    except (TypeError, ValueError):
        code = 0
    return _SEERR_MEDIA_STATUS.get(code, "missing")


def _seerr_search(catalog: ApplicationCatalog, term: str) -> tuple[list[dict[str, Any]], str | None]:
    plugin = catalog.get("seerr")
    key = get_application_api_key("seerr", plugin.config_dir)
    if not key:
        return [], "no Seerr API key; add one in Settings → Integrations"
    headers = {"Content-Type": "application/json", "X-Api-Key": key}
    # Seerr rejects '+' for spaces and unescaped reserved characters in the query.
    data, error = _fetch_json(
        f"http://127.0.0.1:{plugin.port}/api/v1/search?query={quote(term, safe='')}&page=1",
        headers=headers,
    )
    if error:
        if error in ("HTTP 401", "HTTP 403"):
            error = f"{error}: Seerr rejected the API key"
        return [], error
    rows = data.get("results") if isinstance(data, dict) else None
    items: list[dict[str, Any]] = []
    if not isinstance(rows, list):
        return items, "unexpected search payload"
    for row in rows:
        if not isinstance(row, dict):
            continue
        media_type = str(row.get("mediaType") or "").lower()
        if media_type not in {"movie", "tv"}:
            continue
        title = row.get("title") or row.get("name") or "Title"
        poster = row.get("posterPath")
        status = seerr_media_status(row)
        items.append(
            {
                "source": "seerr",
                "mediaType": media_type,
                "mediaId": row.get("id"),
                "title": title,
                "year": row.get("releaseDate") or row.get("firstAirDate") or "",
                "poster": f"https://image.tmdb.org/t/p/w154{poster}" if poster else "",
                "status": status,
                "can_request": status in {"missing", "partial"},
            }
        )
        if len(items) >= 20:
            break
    return items, None


def _sonarr_lookup(catalog: ApplicationCatalog, term: str) -> list[dict[str, Any]]:
    plugin = catalog.get("sonarr")
    data = _get_json(
        f"http://127.0.0.1:{plugin.port}/api/v3/series/lookup",
        headers=_arr_headers("sonarr", plugin.config_dir),
        params={"term": term},
    )
    items: list[dict[str, Any]] = []
    if not isinstance(data, list):
        return items
    for row in data[:10]:
        if not isinstance(row, dict):
            continue
        items.append(
            {
                "source": "sonarr",
                "mediaType": "tv",
                "mediaId": row.get("tvdbId"),
                "title": row.get("title") or "Series",
                "year": str(row.get("year") or ""),
                "poster": row.get("remotePoster") or "",
                "status": _sonarr_status(row),
                "can_request": False,
            }
        )
    return items


def _radarr_lookup(catalog: ApplicationCatalog, term: str) -> list[dict[str, Any]]:
    plugin = catalog.get("radarr")
    data = _get_json(
        f"http://127.0.0.1:{plugin.port}/api/v3/movie/lookup",
        headers=_arr_headers("radarr", plugin.config_dir),
        params={"term": term},
    )
    items: list[dict[str, Any]] = []
    if not isinstance(data, list):
        return items
    for row in data[:10]:
        if not isinstance(row, dict):
            continue
        items.append(
            {
                "source": "radarr",
                "mediaType": "movie",
                "mediaId": row.get("tmdbId"),
                "title": row.get("title") or "Movie",
                "year": str(row.get("year") or ""),
                "poster": row.get("remotePoster") or "",
                "status": _radarr_status(row),
                "can_request": False,
            }
        )
    return items


def _sonarr_status(row: dict[str, Any]) -> str:
    if not row.get("id"):
        return "missing"
    stats = row.get("statistics") if isinstance(row.get("statistics"), dict) else {}
    try:
        percent = float(stats.get("percentOfEpisodes") or 0)
    except (TypeError, ValueError):
        percent = 0.0
    if percent >= 100:
        return "available"
    return "partial" if percent > 0 else "monitored"


def _radarr_status(row: dict[str, Any]) -> str:
    if not row.get("id"):
        return "missing"
    return "available" if row.get("hasFile") else "monitored"


def _pct(value: Any) -> int:
    try:
        return max(0, min(100, int(round(float(value)))))
    except (TypeError, ValueError):
        return 0
