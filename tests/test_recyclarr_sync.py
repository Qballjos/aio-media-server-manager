"""Recyclarr sync runs for minutes; it must not freeze the manager's API meanwhile."""

import asyncio
import threading

from fastapi.testclient import TestClient

from api.app import create_app
from api.routers import recyclarr as recyclarr_router
from core import recyclarr


def test_sync_endpoint_runs_recyclarr_off_the_event_loop(monkeypatch):
    seen: list[str] = []

    def fake_run_sync():
        try:
            asyncio.get_running_loop()
            seen.append("on-loop")
        except RuntimeError:
            seen.append("worker")
        return {"ok": True, "detail": "Sync finished.", "log": ""}

    monkeypatch.setattr(recyclarr_router, "run_sync", fake_run_sync)
    res = TestClient(create_app()).post("/api/recyclarr/sync")
    assert res.status_code == 200
    assert seen == ["worker"]


def test_second_sync_while_one_runs_returns_immediately(monkeypatch):
    started, release = threading.Event(), threading.Event()
    calls: list[str] = []

    def slow_sync(timeout: float = 180.0):
        calls.append("run")
        started.set()
        release.wait(5)
        return {"ok": True, "detail": "Sync finished.", "log": ""}

    monkeypatch.setattr(recyclarr, "_run_sync_unlocked", slow_sync)
    results: list[dict] = []
    first = threading.Thread(target=lambda: results.append(recyclarr.run_sync()))
    first.start()
    assert started.wait(5)
    second = recyclarr.run_sync()
    release.set()
    first.join(5)
    assert calls == ["run"]
    assert second["ok"] is False
    assert "already running" in second["detail"]
    assert results[0]["ok"] is True
