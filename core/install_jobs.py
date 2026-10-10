"""In-memory catalog install job status for the wizard and catalog UI."""

from __future__ import annotations

import threading
import time
from typing import Any

_lock = threading.Lock()
_jobs: dict[str, dict[str, Any]] = {}
_wiring_progress: dict[str, Any] = {}


def set_job(name: str, status: str, message: str = "", *, wiring: bool = False) -> dict[str, Any]:
    row = {
        "name": name,
        "status": status,
        "message": message or "",
        "updated_at": time.time(),
        "wiring": wiring,
    }
    with _lock:
        previous = _jobs.get(name)
        if previous and all(previous.get(key) == row[key] for key in ("status", "message", "wiring")):
            row["updated_at"] = previous["updated_at"]
        _jobs[name] = row
        return _public_job(row)


def update_job(name: str, message: str) -> None:
    with _lock:
        row = _jobs.get(name)
        if row and row["status"] in {"queued", "installing", "configuring"} and row["message"] != message:
            row.update(message=message, updated_at=time.time())


def set_wiring_progress(message: str) -> None:
    with _lock:
        if message != _wiring_progress.get("message"):
            _wiring_progress.update(message=message, updated_at=time.time())


def _public_job(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    if result.pop("wiring", False) and _wiring_progress.get("message"):
        result.update(
            message="Shared setup: " + _wiring_progress["message"],
            updated_at=_wiring_progress["updated_at"],
        )
    return result


def get_job(name: str) -> dict[str, Any] | None:
    with _lock:
        row = _jobs.get(name)
        return _public_job(row) if row else None


def snapshot() -> list[dict[str, Any]]:
    with _lock:
        return [_public_job(row) for row in _jobs.values()]


def clear_jobs() -> None:
    with _lock:
        _jobs.clear()
        _wiring_progress.clear()
