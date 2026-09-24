"""Household homepage snapshot: launcher plus widgets from installed app APIs."""

from __future__ import annotations

import logging
from calendar import monthrange
from datetime import date, timedelta
from typing import Any, Optional
import requests

from applications.catalog import ApplicationCatalog
from core.integrations.credentials import get_application_api_key
from core.integrations.nzbget import NZBGetClient
from core.integrations.plex import PlexClient
from core.integrations.qbittorrent import QBittorrentClient
from core.supervisor import ProcessSupervisor

logger = logging.getLogger(__name__)

_TIMEOUT = 4.0
_LAUNCHER_SKIP = frozenset({"recyclarr"})


def month_calendar_span(today: date | None = None) -> tuple[date, date]:
    """Monday–Sunday grid covering the current month (including leading/trailing days)."""
    today = today or date.today()
    first = today.replace(day=1)
    start = first - timedelta(days=first.weekday())
    last = today.replace(day=monthrange(today.year, today.month)[1])
    end = last + timedelta(days=(6 - last.weekday()))
    return start, end


def homepage_snapshot(host: str) -> dict[str, Any]:
    catalog = ApplicationCatalog()
    running = _running_names()
    start, end = month_calendar_span()
    notes: list[dict[str, Any]] = []

    apps = _launcher_apps(catalog, running, host)

    calendar: list[dict[str, Any]] = []
    calendar.extend(_collect_sonarr_calendar(catalog, running, start, end, notes))
    calendar.extend(_collect_radarr_calendar(catalog, running, start, end, notes))
    calendar.sort(key=lambda item: (item.get("when") or "", item.get("title") or ""))

    downloads: list[dict[str, Any]] = []
    downloads.extend(_collect_sabnzbd_queue(catalog, running, notes))
    downloads.extend(_collect_nzbget_queue(catalog, running, notes))
    downloads.extend(_collect_qbittorrent_queue(catalog, running, notes))

    recent: list[dict[str, Any]] = []
    recent.extend(_collect_jellyfin_recent(catalog, running, notes))
    recent.extend(_collect_plex_recent(catalog, running, notes))

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
        "calendar": calendar[:250],
        "downloads": downloads[:40],
        "recent": recent[:24],
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
        return {"query": term, "results": [], "seerr": False}
    if catalog.has("seerr") and catalog.get("seerr").is_installed() and "seerr" in running:
        results = _seerr_search(catalog, term)
        return {"query": term, "results": results, "seerr": True}
    results: list[dict[str, Any]] = []
    if catalog.has("sonarr") and catalog.get("sonarr").is_installed() and "sonarr" in running:
        results.extend(_sonarr_lookup(catalog, term))
    if catalog.has("radarr") and catalog.get("radarr").is_installed() and "radarr" in running:
        results.extend(_radarr_lookup(catalog, term))
    return {"query": term, "results": results[:20], "seerr": False}


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
    apps.sort(key=lambda item: item["display_name"].lower())
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


def _get_json(url: str, *, headers: Optional[dict[str, str]] = None, params: Optional[dict[str, Any]] = None) -> Any:
    data, _error = _fetch_json(url, headers=headers, params=params)
    return data


def _fetch_json(
    url: str,
    *,
    headers: Optional[dict[str, str]] = None,
    params: Optional[dict[str, Any]] = None,
) -> tuple[Any, str | None]:
    try:
        resp = requests.get(url, headers=headers or {}, params=params, timeout=_TIMEOUT)
        if resp.status_code == 200:
            return resp.json(), None
        return None, f"HTTP {resp.status_code}"
    except requests.Timeout:
        return None, "timed out after 4s"
    except Exception as exc:
        logger.debug("Homepage GET %s failed: %s", url, exc)
        return None, str(exc)[:180]


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
        "calendar is empty this month",
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
                "when": str(row.get("airDateUtc") or row.get("airDate") or "")[:16],
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
        "calendar is empty this month",
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
                "when": str(when)[:16],
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
) -> list[dict[str, Any]]:
    if not _source_ready(catalog, running, "jellyfin", "recent", notes, need_key=True):
        return []
    plugin = catalog.get("jellyfin")
    key = get_application_api_key("jellyfin", plugin.config_dir)
    headers = {"Content-Type": "application/json"}
    if key:
        headers["X-Emby-Token"] = key
        headers["X-MediaBrowser-Token"] = key
    data, error = _fetch_json(
        f"http://127.0.0.1:{plugin.port}/Items",
        headers=headers,
        params={
            "Recursive": "true",
            "SortBy": "DateCreated",
            "SortOrder": "Descending",
            "IncludeItemTypes": "Movie,Episode,Series",
            "Limit": "16",
            "Fields": "DateCreated",
        },
    )
    rows = data.get("Items") if isinstance(data, dict) else None
    items: list[dict[str, Any]] = []
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            items.append(
                {
                    "source": "jellyfin",
                    "title": row.get("Name") or "Item",
                    "detail": row.get("Type") or "",
                    "when": str(row.get("DateCreated") or "")[:16],
                }
            )
    payload_error = None if isinstance(data, dict) else "unexpected items payload"
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
        for row in rows[:16]:
            if not isinstance(row, dict):
                continue
            items.append(
                {
                    "source": "plex",
                    "title": row.get("title") or row.get("parentTitle") or "Item",
                    "detail": row.get("type") or "",
                    "when": str(row.get("addedAt") or row.get("originallyAvailableAt") or ""),
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


def _seerr_search(catalog: ApplicationCatalog, term: str) -> list[dict[str, Any]]:
    plugin = catalog.get("seerr")
    key = get_application_api_key("seerr", plugin.config_dir)
    headers = {"Content-Type": "application/json"}
    if key:
        headers["X-Api-Key"] = key
    data = _get_json(
        f"http://127.0.0.1:{plugin.port}/api/v1/search",
        headers=headers,
        params={"query": term, "page": 1},
    )
    rows = data.get("results") if isinstance(data, dict) else None
    items: list[dict[str, Any]] = []
    if not isinstance(rows, list):
        return items
    for row in rows[:20]:
        if not isinstance(row, dict):
            continue
        media_type = str(row.get("mediaType") or "").lower()
        title = row.get("title") or row.get("name") or "Title"
        poster = row.get("posterPath")
        items.append(
            {
                "source": "seerr",
                "mediaType": "tv" if media_type in {"tv", "series"} else "movie",
                "mediaId": row.get("id"),
                "title": title,
                "year": row.get("releaseDate") or row.get("firstAirDate") or "",
                "poster": f"https://image.tmdb.org/t/p/w154{poster}" if poster else "",
                "can_request": True,
            }
        )
    return items


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
                "can_request": False,
            }
        )
    return items


def _pct(value: Any) -> int:
    try:
        return max(0, min(100, int(round(float(value)))))
    except (TypeError, ValueError):
        return 0
