"""Small, cached, credential-free Homey projection. Never returns service URLs or users."""

from datetime import datetime, timezone
import math
import threading
import time

from applications.catalog import ApplicationCatalog
from core.homepage import (
    _collect_jellyfin_recent,
    _collect_plex_recent,
    _running_names,
    _when_sort_key,
)
from core.homepage_status import now_playing
from core.version import app_version

_lock = threading.Lock()
_cache = None
_expires = 0.0


def text(value, limit=240):
    return "".join(c for c in str(value or "") if c >= " " and c != "\x7f")[:limit]


def project_playing(rows):
    result = []
    for row in rows[:20]:
        progress = row.get("progress")
        if not isinstance(progress, (int, float)) or not math.isfinite(progress):
            progress = 0
        result.append(
            {
                "title": text(row.get("title")),
                "detail": text(row.get("detail")),
                "source": text(row.get("source"), 32),
                "progress": max(0, min(100, round(progress))),
                "paused": row.get("paused") is True,
            }
        )
    return result


def recent():
    catalog, running, notes = ApplicationCatalog(), _running_names(), []
    rows = _collect_jellyfin_recent(
        catalog, running, notes, "127.0.0.1", read_only=True
    )
    rows += _collect_plex_recent(catalog, running, notes, "127.0.0.1")
    if any(note.get("state") == "error" for note in notes):
        raise RuntimeError("Recent library source unavailable")
    rows.sort(key=_when_sort_key, reverse=True)
    return [
        {
            "title": text(row.get("title")),
            "detail": text(row.get("detail")),
            "source": text(row.get("source"), 32),
            "addedAt": text(row.get("when"), 64),
        }
        for row in rows[:12]
    ]


def dashboard():
    global _cache, _expires
    with _lock:
        if _cache is not None and time.monotonic() < _expires:
            return _cache
        result = {
            "schemaVersion": 1,
            "version": app_version(),
            "updatedAt": datetime.now(timezone.utc).isoformat(),
        }
        for key, read in (
            ("playing", lambda: project_playing(now_playing("127.0.0.1", strict=True))),
            ("recent", recent),
        ):
            try:
                result[key] = {"state": "ready", "items": read()}
            except Exception:
                # Do not export provider errors, paths or credentials. Failed reads are never shown as empty libraries.
                result[key] = {"state": "unavailable", "items": []}
        _cache, _expires = result, time.monotonic() + 30
        return result
