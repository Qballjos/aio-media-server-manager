"""Localhost and Diagnostics-switch access to host debug data."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from core.auth import auth_manager
from core.diagnostics import diagnostics
from core.settings import Settings


def _local_client() -> TestClient:
    return TestClient(create_app(), base_url="http://127.0.0.1", client=("127.0.0.1", 50000))


def _remote_client() -> TestClient:
    return TestClient(create_app())


@pytest.fixture(autouse=True)
def isolated_debug(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    test_settings = Settings(
        config_dir=tmp_path / "config",
        download_dir=tmp_path / "downloads",
        media_dir=tmp_path / "media",
        install_dir=tmp_path / "apps",
    )
    test_settings.initialise()
    monkeypatch.setattr(auth_manager, "_settings", test_settings)
    monkeypatch.setattr("core.settings.settings.config_dir", test_settings.config_dir)
    monkeypatch.setattr(diagnostics, "_share_path", lambda: tmp_path / "debug_share.json")
    diagnostics.revoke_share()
    auth_manager._rate._hits.clear()
    yield
    diagnostics.revoke_share()
    auth_manager._rate._hits.clear()


def _login(client: TestClient) -> dict[str, str]:
    setup = client.post(
        "/api/auth/setup",
        json={"username": "admin", "email": "admin@example.com", "password": "StrongPassword123!"},
    )
    assert setup.status_code == 200
    token = setup.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_system_info_not_public_on_lan():
    resp = _remote_client().get("/api/system/info")
    assert resp.status_code == 401


def test_localhost_system_info_without_login():
    resp = _local_client().get("/api/system/info")
    assert resp.status_code == 200
    data = resp.json()
    assert data["debug"] is True
    assert "storage" in data
    assert "metrics" in data
    assert "processes" in data


def test_cloudflare_headers_are_not_treated_as_localhost():
    client = _local_client()
    resp = client.get("/api/system/info", headers={"CF-Connecting-IP": "203.0.113.10"})
    assert resp.status_code == 401


def test_session_without_debug_switch_gets_operational_info_only():
    client = _remote_client()
    headers = _login(client)
    resp = client.get("/api/system/info", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["debug"] is False
    assert "vpn" in data
    assert "transcoding" in data
    assert "metrics" in data
    assert "cpu_percent" in data["metrics"]
    assert "storage" not in data
    assert "settings" not in data
    assert "processes" not in data


def test_debug_switch_unlocks_full_system_info_for_session():
    client = _remote_client()
    headers = _login(client)
    created = client.post("/api/diagnostics/share", headers=headers)
    assert created.status_code == 200
    resp = client.get("/api/system/info", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["debug"] is True
    assert "storage" in data
    assert "metrics" in data


def test_process_logs_require_localhost_or_debug_switch():
    remote = _remote_client()
    headers = _login(remote)
    denied = remote.get("/api/system/processes/sonarr/logs", headers=headers)
    assert denied.status_code == 403

    local = _local_client()
    allowed = local.get("/api/system/processes/sonarr/logs")
    assert allowed.status_code in {200, 404}


def test_diagnostics_errors_hidden_until_debug_switch_or_localhost(tmp_path: Path):
    diagnostics.record_error("unit", "hidden unless debug")
    remote = _remote_client()
    headers = _login(remote)
    hidden = remote.get("/api/diagnostics", headers=headers)
    assert hidden.status_code == 200
    assert hidden.json()["errors"] == []

    remote.post("/api/diagnostics/share", headers=headers)
    shown = remote.get("/api/diagnostics", headers=headers)
    assert any("hidden unless debug" in item["message"] for item in shown.json()["errors"])

    local = _local_client()
    diagnostics.revoke_share()
    from_box = local.get("/api/diagnostics", headers=headers)
    assert from_box.status_code == 200
    assert any("hidden unless debug" in item["message"] for item in from_box.json()["errors"])
