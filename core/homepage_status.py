"""Home's status widgets: who is watching, free disk space, CPU and memory, and what needs a look."""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

import psutil
import requests

from applications.catalog import ApplicationCatalog
from core.homepage import _TIMEOUT, _as_int, _fetch_json, _running_names, _web_url
from core.crypto import secret_store
from core.integrations.jellyfin import jellyfin_auth_headers
from core.integrations.plex import PlexClient
from core.metrics import collect_metrics
from core.settings import settings

logger = logging.getLogger(__name__)

JELLYFIN_TICKS_PER_MINUTE = 600_000_000
PLEX_MS_PER_MINUTE = 60_000
FULL_PERCENT = 90
# Process states, VPN/tunnel and updates change slowly; Home asks every few seconds.
_ATTENTION_TTL = 60.0
_attention_cache: tuple[float, dict[str, Any]] | None = None
_attention_lock = threading.Lock()


def human_bytes(value: float) -> str:
    """Same steps as the dashboard's formatBytes: 1024-based, one decimal under 10."""
    number = float(value or 0)
    if number < 1024:
        return f"{round(number)} B"
    for unit in ("KB", "MB", "GB", "TB"):
        number /= 1024
        if number < 1024 or unit == "TB":
            return f"{number:.0f} {unit}" if number >= 10 else f"{number:.1f} {unit}"
    return f"{number:.0f} TB"


def _episode_code(season: int | None, episode: int | None) -> str:
    return f"S{season:02d}E{episode:02d}" if season is not None and episode is not None else ""


def _joined(*parts: Any) -> str:
    return " · ".join(str(part) for part in parts if part)


def _progress(position: int, runtime: int) -> int:
    if runtime <= 0:
        return 0
    return max(0, min(100, round(position / runtime * 100)))


def _minutes_left(position: int, runtime: int, per_minute: int) -> int | None:
    if runtime <= 0:
        return None
    return max(0, round((runtime - position) / per_minute))


def _art(source: str, item_id: str) -> str:
    return f"/api/homepage/art?source={source}&item_id={quote(item_id, safe='')}" if item_id else ""


def parse_jellyfin_sessions(rows: Any, web_base: str) -> list[dict[str, Any]]:
    """Jellyfin's /Sessions: only the ones playing something, newest first as Jellyfin lists them."""
    out: list[dict[str, Any]] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or not isinstance(row.get("NowPlayingItem"), dict):
            continue
        item = row["NowPlayingItem"]
        state = row.get("PlayState") if isinstance(row.get("PlayState"), dict) else {}
        kind = str(item.get("Type") or "")
        item_id = str(item.get("Id") or "")
        if kind == "Episode":
            title = item.get("SeriesName") or item.get("Name") or "Episode"
            detail = _joined(_episode_code(_as_int(item.get("ParentIndexNumber")), _as_int(item.get("IndexNumber"))), item.get("Name"))
            poster_id = str(item.get("SeriesId") or item_id)
        elif kind == "Audio":
            title = item.get("Name") or "Track"
            detail = _joined(item.get("AlbumArtist"), item.get("Album"))
            poster_id = str(item.get("AlbumId") or item_id)
        else:
            title = item.get("Name") or kind or "Playing"
            detail = str(item.get("ProductionYear") or "")
            poster_id = item_id
        runtime = _as_int(item.get("RunTimeTicks")) or 0
        position = _as_int(state.get("PositionTicks")) or 0
        out.append(
            {
                "source": "jellyfin",
                "user": str(row.get("UserName") or ""),
                "device": str(row.get("DeviceName") or row.get("Client") or ""),
                "title": str(title),
                "detail": detail,
                "poster": _art("jellyfin", poster_id),
                "url": f"{web_base}/web/#/details?id={quote(item_id, safe='')}" if item_id and web_base else "",
                "progress": _progress(position, runtime),
                "paused": bool(state.get("IsPaused")),
                "transcoding": state.get("PlayMethod") == "Transcode",
                "minutes_left": _minutes_left(position, runtime, JELLYFIN_TICKS_PER_MINUTE),
            }
        )
    return out


def parse_plex_sessions(payload: Any, web_base: str) -> list[dict[str, Any]]:
    """Plex's /status/sessions."""
    container = payload.get("MediaContainer") if isinstance(payload, dict) else None
    rows = container.get("Metadata") if isinstance(container, dict) else None
    out: list[dict[str, Any]] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        kind = str(row.get("type") or "")
        key = str(row.get("ratingKey") or "")
        if kind == "episode":
            title = row.get("grandparentTitle") or row.get("title") or "Episode"
            detail = _joined(_episode_code(_as_int(row.get("parentIndex")), _as_int(row.get("index"))), row.get("title"))
            poster_id = str(row.get("grandparentRatingKey") or key)
        elif kind == "track":
            title = row.get("title") or "Track"
            detail = _joined(row.get("grandparentTitle"), row.get("parentTitle"))
            poster_id = str(row.get("parentRatingKey") or key)
        else:
            title = row.get("title") or kind or "Playing"
            detail = str(row.get("year") or "")
            poster_id = key
        player = row.get("Player") if isinstance(row.get("Player"), dict) else {}
        user = row.get("User") if isinstance(row.get("User"), dict) else {}
        transcode = row.get("TranscodeSession") if isinstance(row.get("TranscodeSession"), dict) else {}
        duration = _as_int(row.get("duration")) or 0
        offset = _as_int(row.get("viewOffset")) or 0
        out.append(
            {
                "source": "plex",
                "user": str(user.get("title") or ""),
                "device": str(player.get("title") or player.get("product") or ""),
                "title": str(title),
                "detail": detail,
                "poster": _art("plex", poster_id),
                "url": f"{web_base}/web/index.html#!/server/library/metadata/{quote(key, safe='')}" if key and web_base else "",
                "progress": _progress(offset, duration),
                "paused": player.get("state") == "paused",
                "transcoding": "transcode" in (transcode.get("videoDecision"), transcode.get("audioDecision")),
                "minutes_left": _minutes_left(offset, duration, PLEX_MS_PER_MINUTE),
            }
        )
    return out


def _installed_and_running(catalog: ApplicationCatalog, running: set[str], name: str) -> bool:
    return catalog.has(name) and catalog.get(name).is_installed() and name in running


def now_playing(host: str, scheme: str = "http") -> list[dict[str, Any]]:
    catalog = ApplicationCatalog()
    running = _running_names()
    rows: list[dict[str, Any]] = []
    if _installed_and_running(catalog, running, "jellyfin"):
        plugin = catalog.get("jellyfin")
        # Only the stored key: finding one logs in to Jellyfin, which the Home snapshot already does single-flight.
        key = secret_store.get_secret("jellyfin_api_key")
        if key:
            data, error = _fetch_json(
                f"http://127.0.0.1:{plugin.port}/Sessions",
                headers=jellyfin_auth_headers(key),
                params={"ActiveWithinSeconds": "960"},
            )
            if error:
                logger.debug("Jellyfin sessions failed: %s", error)
            rows += parse_jellyfin_sessions(data, _web_url(plugin.name, plugin.port, host, scheme))
    if _installed_and_running(catalog, running, "plex"):
        plugin = catalog.get("plex")
        client = PlexClient(port=plugin.port, config_dir=plugin.config_dir)
        try:
            resp = requests.get(f"{client.base_url}/status/sessions", headers=client._headers(), timeout=_TIMEOUT)
            if resp.status_code == 200:
                rows += parse_plex_sessions(resp.json(), _web_url(plugin.name, plugin.port, host, scheme))
        except Exception as exc:
            logger.debug("Plex sessions failed: %s", exc)
    return rows


def _mount_device(path: Path, partitions: list[Any]) -> str:
    """The device of the deepest mount holding `path`, or '' when the mount table does not say."""
    text = str(path)
    best, device = "", ""
    for part in partitions:
        mount = str(getattr(part, "mountpoint", "") or "")
        if not mount:
            continue
        inside = mount == "/" or text == mount or text.startswith(mount.rstrip("/") + "/")
        if inside and len(mount) > len(best):
            best, device = mount, str(getattr(part, "device", "") or "")
    return device


def storage_volumes(
    paths: dict[str, Path],
    *,
    stat: Callable[[Path], Any] = os.stat,
    usage: Callable[[str], Any] = psutil.disk_usage,
    partitions: list[Any] | None = None,
) -> list[dict[str, Any]]:
    """
    One row per disk: data paths on the same device share it. The mount table decides, because btrfs subvolumes
    (every Synology shared folder) each get their own st_dev on one disk; st_dev is the fallback. Missing paths are
    left out. Fullest first.
    """
    if partitions is None:
        try:
            partitions = psutil.disk_partitions(all=True)
        except Exception:
            partitions = []
    volumes: dict[str, dict[str, Any]] = {}
    for label, raw in paths.items():
        path = Path(raw)
        try:
            if not path.exists():
                continue
            device = _mount_device(path.resolve(), partitions) or f"st_dev:{stat(path).st_dev}"
        except OSError:
            continue
        if device in volumes:
            volumes[device]["labels"].append(label)
            continue
        try:
            used = usage(str(path))
        except Exception:
            continue
        volumes[device] = {"labels": [label], "total": int(used.total), "used": int(used.used), "free": int(used.free), "percent": float(used.percent)}
    return sorted(volumes.values(), key=lambda volume: -volume["percent"])


def server_summary(metrics: dict[str, Any], boot_time: float, now: float) -> dict[str, Any]:
    memory = metrics.get("memory") if isinstance(metrics.get("memory"), dict) else {}
    total = int(memory.get("total") or 0)
    available = int(memory.get("available") or 0)
    readings = [
        float(entry["current"])
        for entries in (metrics.get("temperatures") or {}).values()
        for entry in entries
        if isinstance(entry, dict) and isinstance(entry.get("current"), (int, float))
    ]
    network = metrics.get("network") if isinstance(metrics.get("network"), dict) else {}
    return {
        "cpu_percent": float(metrics.get("cpu_percent") or 0),
        "cpu_count": int(metrics.get("cpu_count") or 1),
        "memory_percent": float(memory.get("percent") or 0),
        "memory_used": max(0, total - available),
        "memory_total": total,
        "uptime_seconds": max(0, int(now - boot_time)) if boot_time else 0,
        "temperature": max(readings) if readings else None,
        # Counters since boot; the dashboard turns two samples into a rate.
        "network": {"rx_bytes": int(network.get("bytes_recv") or 0), "tx_bytes": int(network.get("bytes_sent") or 0)},
        "sampled_at": now,
    }


def attention_items(snap: dict[str, Any], names: dict[str, str], volumes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """What the notifications would report, as rows to act on: problems, then full disks, then updates."""
    items: list[dict[str, Any]] = []
    sick = snap.get("sick_apps") or {}
    for name in sorted(sick, key=lambda app: (names.get(app) or app).lower()):
        what = "keeps crashing" if sick[name] == "crash_loop" else "failed to start"
        items.append({"level": "problem", "title": f"{names.get(name) or name} {what}", "detail": "Open its logs in Catalog.", "href": f"#/catalog?q={quote(name)}"})
    if snap.get("vpn_up") is False:
        items.append({"level": "problem", "title": "VPN is not connected", "detail": "Apps that download through it wait until it reconnects.", "href": "#/settings/network"})
    if snap.get("tunnel_up") is False:
        items.append({"level": "problem", "title": "Cloudflare tunnel is down", "detail": "Your public addresses are unreachable.", "href": "#/settings/network"})
    for volume in volumes:
        if volume["percent"] >= FULL_PERCENT:
            items.append(
                {
                    "level": "warning",
                    "title": f"{' · '.join(volume['labels'])} is {round(volume['percent'])}% full",
                    "detail": f"{human_bytes(volume['free'])} free",
                    "href": "#/settings/system",
                }
            )
    updates = [str(name) for name in snap.get("updates") or []]
    if updates:
        more = f" and {len(updates) - 3} more" if len(updates) > 3 else ""
        items.append(
            {
                "level": "info",
                "title": f"{len(updates)} update{'' if len(updates) == 1 else 's'} available",
                "detail": ", ".join(updates[:3]) + more,
                "href": "#/settings/updates",
            }
        )
    return items


def _attention_snapshot() -> dict[str, Any]:
    global _attention_cache
    from core import notifications

    with _attention_lock:
        now = time.monotonic()
        if _attention_cache and now - _attention_cache[0] < _ATTENTION_TTL:
            return _attention_cache[1]
        # Without its disk check: that writes a test file into each data folder, and Home has the volumes already.
        snap = notifications.snapshot(disks=False)
        _attention_cache = (now, snap)
        return snap


def _display_names(snap: dict[str, Any]) -> dict[str, str]:
    catalog = ApplicationCatalog()
    return {name: catalog.get(name).manifest.display_name for name in snap.get("sick_apps") or {} if catalog.has(name)}


def _safe(part: str, build: Callable[[], Any], fallback: Any) -> Any:
    try:
        return build()
    except Exception as exc:
        logger.debug("Home status %s failed: %s", part, exc)
        return fallback


def homepage_status(host: str, scheme: str = "http") -> dict[str, Any]:
    paths = {"Config": settings.config_dir, "Downloads": settings.download_dir, "Media": settings.media_dir}
    volumes = _safe("storage", lambda: storage_volumes(paths), [])

    def attention() -> list[dict[str, Any]]:
        snap = _attention_snapshot()
        return attention_items(snap, _display_names(snap), volumes)

    return {
        "playing": _safe("playing", lambda: now_playing(host, scheme), []),
        "server": _safe("server", lambda: server_summary(collect_metrics(), psutil.boot_time(), time.time()), None),
        "storage": volumes,
        "attention": _safe("attention", attention, []),
    }
