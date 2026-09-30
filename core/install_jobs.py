"""In-memory catalog install job status for the wizard and catalog UI."""

from __future__ import annotations

import threading
import time
from typing import Any

_lock = threading.Lock()
_jobs: dict[str, dict[str, Any]] = {}


def set_job(name: str, status: str, message: str = "") -> dict[str, Any]:
    row = {
        "name": name,
        "status": status,
        "message": message or "",
        "updated_at": time.time(),
    }
    with _lock:
        _jobs[name] = row
        return dict(row)


def get_job(name: str) -> dict[str, Any] | None:
    with _lock:
        row = _jobs.get(name)
        return dict(row) if row else None


def snapshot() -> list[dict[str, Any]]:
    with _lock:
        return [dict(row) for row in _jobs.values()]


def clear_jobs() -> None:
    with _lock:
        _jobs.clear()
