"""Installation progress stays accurate without querying application services."""

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core import install_jobs as jobs


@pytest.fixture(autouse=True)
def job_clock(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(jobs, "_jobs", {})
    monkeypatch.setattr(jobs, "_wiring_progress", {})
    monkeypatch.setattr(jobs, "time", SimpleNamespace(time=lambda: clock[0]))
    return clock


def test_job_timestamps_change_only_when_activity_changes(job_clock):
    original = jobs.set_job("seerr", "configuring", "Starting application")
    job_clock[0] = 200.0
    assert jobs.set_job("seerr", "configuring", "Starting application") == original
    jobs.update_job("seerr", "Starting application")
    assert jobs.get_job("seerr") == original

    jobs.update_job("seerr", "Waiting for application to respond")
    assert jobs.get_job("seerr")["updated_at"] == 200.0
    job_clock[0] = 300.0
    jobs.update_job("seerr", "Waiting for application to respond")
    assert jobs.get_job("seerr")["updated_at"] == 200.0
    assert jobs.set_job("seerr", "started")["updated_at"] == 300.0


@pytest.mark.parametrize("status", ["started", "failed", "already_installed"])
def test_progress_updates_do_not_create_jobs_or_change_terminal_jobs(status, job_clock):
    original = jobs.set_job("seerr", status, "Finished")
    job_clock[0] = 200.0
    jobs.update_job("missing", "Downloading")
    jobs.update_job("seerr", "Downloading")
    assert jobs.get_job("missing") is None
    assert jobs.get_job("seerr") == original


def test_shared_progress_only_overlays_jobs_waiting_for_shared_setup(job_clock):
    jobs.set_job("seerr", "configuring", "Waiting for shared setup", wiring=True)
    startup = jobs.set_job("jellyfin", "configuring", "Waiting for application to respond")
    installing = jobs.set_job("sonarr", "installing", "Extracting application")
    queued = jobs.set_job("radarr", "queued", "Waiting to start installation")
    job_clock[0] = 200.0
    jobs.set_wiring_progress("Reading Prowlarr's indexer catalog")
    shared = jobs.get_job("seerr")
    assert shared["message"] == "Shared setup: Reading Prowlarr's indexer catalog"
    assert shared["updated_at"] == 200.0
    assert "wiring" not in shared
    assert jobs.get_job("jellyfin") == startup
    assert jobs.get_job("sonarr") == installing
    assert jobs.get_job("radarr") == queued

    job_clock[0] = 300.0
    jobs.set_wiring_progress("Reading Prowlarr's indexer catalog")
    assert jobs.get_job("seerr") == shared
    jobs.set_wiring_progress("Checking and adding indexer: YTS")
    assert jobs.get_job("seerr")["updated_at"] == 300.0
    assert jobs.get_job("seerr")["message"] == "Shared setup: Checking and adding indexer: YTS"
    assert jobs.set_job("seerr", "started")["message"] == ""


def test_job_results_are_copies_and_clear_removes_shared_progress():
    returned = jobs.set_job("seerr", "configuring", "Waiting", wiring=True)
    returned["message"] = "changed"
    jobs.get_job("seerr")["message"] = "also changed"
    rows = jobs.snapshot()
    rows[0]["message"] = "snapshot changed"
    rows.clear()
    assert jobs.get_job("seerr")["message"] == "Waiting"
    jobs.set_wiring_progress("Signing in to Seerr")
    assert jobs.snapshot() == [jobs.get_job("seerr")]
    jobs.clear_jobs()
    assert jobs.snapshot() == []
    assert jobs.get_job("seerr") is None
    assert jobs.set_job("seerr", "configuring", "Waiting", wiring=True)["message"] == "Waiting"


def test_install_jobs_endpoint_requires_auth_and_only_reads_local_progress(tmp_path, monkeypatch):
    import requests
    from api.routers import catalog as catalog_routes
    from core.auth import AuthManager
    from core.settings import Settings

    auth = AuthManager(Settings(config_dir=tmp_path / "config"))
    auth.create_admin("admin", "TestPassword123!")
    monkeypatch.setattr(catalog_routes, "auth_manager", auth)
    monkeypatch.setattr(catalog_routes, "catalog", SimpleNamespace())
    remote_request = Mock(side_effect=AssertionError("Progress must not query remote apps"))
    monkeypatch.setattr(requests.sessions.Session, "request", remote_request)
    app = FastAPI()
    app.include_router(catalog_routes.router)
    client = TestClient(app)
    row = jobs.set_job("seerr", "configuring", "Signing in to Seerr")
    assert client.get("/api/catalog/install-jobs").status_code in (401, 403)
    response = client.get(
        "/api/catalog/install-jobs", headers={"Authorization": f"Bearer {auth.issue_token('admin')}"}
    )
    assert response.status_code == 200
    assert response.json() == {"jobs": [row]}
    remote_request.assert_not_called()


def test_home_shows_queued_uninstalled_app_with_progress(monkeypatch):
    from core import homepage

    def plugin(name):
        return SimpleNamespace(
            name=name, port=5055, is_installed=lambda: False,
            manifest=SimpleNamespace(daemon=True, display_name=name, category=SimpleNamespace(value="requests")),
        )

    catalog = SimpleNamespace(all_plugins=lambda: [plugin("seerr"), plugin("sonarr")])
    monkeypatch.setattr(homepage.settings, "vpn_enabled", False)
    monkeypatch.setattr(homepage, "_web_url", lambda *args: "http://nas.local:5055")
    jobs.set_job("seerr", "queued", "Waiting to start installation")
    rows = homepage._launcher_apps(catalog, set(), "nas.local", processes={})
    assert [row["name"] for row in rows] == ["seerr"]
    assert rows[0]["state"] == "installing"
    assert rows[0]["progress_message"] == "Waiting to start installation"
    assert rows[0]["progress_updated_at"] == 100.0


async def test_shared_wiring_clears_progress_and_releases_lock_on_error(monkeypatch):
    from core.integrations import lifecycle

    monkeypatch.setattr(lifecycle, "_wiring_lock", asyncio.Lock())
    monkeypatch.setattr(lifecycle, "_pending_wiring", 0)
    jobs.set_job("seerr", "configuring", "Waiting for shared setup", wiring=True)

    def fail():
        jobs.set_wiring_progress("Signing in to Seerr")
        assert jobs.get_job("seerr")["message"] == "Shared setup: Signing in to Seerr"
        raise RuntimeError("test wiring failure")

    monkeypatch.setattr(lifecycle.integration_engine, "run_full_wiring", fail)
    with pytest.raises(RuntimeError, match="test wiring failure"):
        await lifecycle.schedule_full_wiring()
    assert jobs.get_job("seerr")["message"] == "Waiting for shared setup"
    assert not lifecycle._wiring_lock.locked()
    assert lifecycle._pending_wiring == 0
    monkeypatch.setattr(lifecycle.integration_engine, "run_full_wiring", lambda: {"status": "completed"})
    assert await lifecycle.schedule_full_wiring() == {"status": "completed"}
    assert jobs.get_job("seerr")["message"] == "Waiting for shared setup"
