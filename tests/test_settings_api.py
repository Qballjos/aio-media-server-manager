"""Settings and account management after first-run."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from api.app import create_app
from api.routers import settings as settings_api
from core.auth import auth_manager
from core.settings import Settings
from core import settings as settings_mod
from core.vpn import VpnManager
from core import vpn as vpn_mod


def _client(tmp_path: Path, monkeypatch) -> tuple[TestClient, Settings]:
    test_settings = Settings(
        config_dir=tmp_path / "config",
        download_dir=tmp_path / "downloads",
        media_dir=tmp_path / "media",
        install_dir=tmp_path / "apps",
    )
    test_settings.initialise()
    monkeypatch.setattr(auth_manager, "_settings", test_settings)
    monkeypatch.setattr(settings_api, "settings", test_settings)
    monkeypatch.setattr(settings_mod, "settings", test_settings)
    mgr = VpnManager(test_settings)
    monkeypatch.setattr(settings_api, "vpn_manager", mgr)
    monkeypatch.setattr(vpn_mod, "vpn_manager", mgr)
    auth_manager._rate._hits.clear()
    return TestClient(create_app()), test_settings


def _auth_headers(client: TestClient) -> dict[str, str]:
    setup = client.post(
        "/api/auth/setup",
        json={
            "username": "admin",
            "email": "admin@example.com",
            "password": "StrongPassword123!",
        },
    )
    assert setup.status_code == 200
    token = setup.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_settings_get_and_patch_general(tmp_path: Path, monkeypatch):
    client, cfg = _client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    res = client.get("/api/settings", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "timezone" in data
    assert data["bind_mounts_editable"] is False
    assert data["updates"]["check_schedule"] in {"off", "daily", "weekly", "monthly"}
    assert "github_token" not in data

    patched = client.patch(
        "/api/settings",
        json={"timezone": "Europe/Amsterdam", "log_level": "DEBUG"},
        headers=headers,
    )
    assert patched.status_code == 200
    body = patched.json()
    assert body["timezone"] == "Europe/Amsterdam"
    assert body["log_level"] == "DEBUG"
    assert cfg.timezone == "Europe/Amsterdam"

    reloaded = Settings(
        config_dir=cfg.config_dir,
        download_dir=cfg.download_dir,
        media_dir=cfg.media_dir,
        install_dir=cfg.install_dir,
    )
    reloaded.initialise()
    assert reloaded.timezone == "Europe/Amsterdam"
    assert reloaded.log_level == "DEBUG"


def test_account_email_update(tmp_path: Path, monkeypatch):
    client, _cfg = _client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    res = client.patch(
        "/api/auth/account",
        json={
            "current_password": "StrongPassword123!",
            "email": "ops@example.com",
        },
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json()["email"] == "ops@example.com"
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {res.json()['access_token']}"})
    assert me.json()["email"] == "ops@example.com"


def test_settings_rejects_anonymous(tmp_path: Path, monkeypatch):
    client, _cfg = _client(tmp_path, monkeypatch)
    assert client.get("/api/settings").status_code == 400
    _auth_headers(client)
    client.cookies.clear()
    assert client.get("/api/settings").status_code == 401


def test_settings_saves_pasted_vpn_config(tmp_path: Path, monkeypatch):
    client, cfg = _client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    profile = "[Interface]\nPrivateKey = dGVzdA==\nAddress = 10.8.0.2/32\n\n[Peer]\nPublicKey = dGVzdA==\n"
    res = client.patch(
        "/api/settings",
        json={"vpn_protocol": "wireguard", "vpn_config_text": profile, "vpn_enabled": False},
        headers=headers,
    )
    assert res.status_code == 200
    dest = cfg.config_dir / "vpn" / "wg0.conf"
    assert dest.is_file()
    assert "[Interface]" in dest.read_text(encoding="utf-8")
    assert dest.stat().st_mode & 0o777 == 0o600
    assert res.json()["vpn"]["config_present"] is True
    bad = client.patch(
        "/api/settings",
        json={"vpn_protocol": "wireguard", "vpn_config_text": "not-a-tunnel"},
        headers=headers,
    )
    assert bad.status_code == 422


def test_settings_vpn_switch_starts_and_stops(tmp_path: Path, monkeypatch):
    from unittest.mock import AsyncMock

    client, cfg = _client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    calls: list[str] = []
    monkeypatch.setattr(
        settings_api.vpn_manager,
        "start",
        lambda: calls.append("start") or {"status": "started", "tunnel_up": True, "enabled": True},
    )
    monkeypatch.setattr(
        settings_api.vpn_manager,
        "stop",
        lambda: calls.append("stop") or {"status": "stopped", "tunnel_up": False, "enabled": False},
    )
    monkeypatch.setattr(
        "core.integrations.lifecycle.stop_tunneled_apps",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "core.integrations.lifecycle.start_tunneled_apps",
        AsyncMock(return_value=[]),
    )

    on = client.patch("/api/settings", json={"vpn_enabled": True}, headers=headers)
    assert on.status_code == 200
    assert cfg.vpn_enabled is True
    assert cfg.vpn_enforce is True
    assert "start" in calls
    assert any("VPN started" in note for note in on.json().get("notes", []))

    off = client.patch("/api/settings", json={"vpn_enabled": False}, headers=headers)
    assert off.status_code == 200
    assert cfg.vpn_enabled is False
    assert cfg.vpn_enforce is False
    assert "stop" in calls
    notes = " ".join(off.json().get("notes", []))
    assert "VPN stopped" in notes
    assert "Kill switch is off" in notes


def test_vpn_api_stop_keeps_kill_switch_when_enabled(tmp_path: Path, monkeypatch):
    from unittest.mock import AsyncMock

    from api.routers import vpn as vpn_api

    client, cfg = _client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    cfg.vpn_enabled = True
    cfg.vpn_enforce = True
    cfg.save()
    monkeypatch.setattr(vpn_api, "vpn_manager", settings_api.vpn_manager)
    monkeypatch.setattr(
        settings_api.vpn_manager,
        "stop",
        lambda: {"status": "stopped", "tunnel_up": False, "enabled": True},
    )
    monkeypatch.setattr(
        "core.integrations.lifecycle.stop_tunneled_apps",
        AsyncMock(return_value=["qbittorrent"]),
    )
    enforce = AsyncMock(return_value=["qbittorrent"])
    start_apps = AsyncMock(return_value=["qbittorrent"])
    monkeypatch.setattr("core.integrations.lifecycle.enforce_vpn_isolation", enforce)
    monkeypatch.setattr("core.integrations.lifecycle.start_tunneled_apps", start_apps)

    res = client.post("/api/vpn/stop", headers=headers)
    assert res.status_code == 200
    assert cfg.vpn_enabled is True
    assert cfg.vpn_enforce is True
    assert res.json().get("started_apps") == []
    enforce.assert_awaited()
    start_apps.assert_not_awaited()


def test_vpn_api_restart_keeps_enabled(tmp_path: Path, monkeypatch):
    from unittest.mock import AsyncMock

    from api.routers import vpn as vpn_api

    client, cfg = _client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    cfg.vpn_enabled = True
    cfg.vpn_enforce = True
    cfg.save()
    calls: list[str] = []
    monkeypatch.setattr(vpn_api, "vpn_manager", settings_api.vpn_manager)
    monkeypatch.setattr(
        settings_api.vpn_manager,
        "stop",
        lambda: calls.append("stop") or {"status": "stopped", "tunnel_up": False},
    )
    monkeypatch.setattr(
        settings_api.vpn_manager,
        "start",
        lambda: calls.append("start") or {"status": "started", "tunnel_up": True, "enabled": True},
    )
    monkeypatch.setattr(
        "core.integrations.lifecycle.stop_tunneled_apps",
        AsyncMock(return_value=["prowlarr"]),
    )
    monkeypatch.setattr(
        "core.integrations.lifecycle.start_tunneled_apps",
        AsyncMock(return_value=["prowlarr"]),
    )

    res = client.post("/api/vpn/restart", headers=headers)
    assert res.status_code == 200
    assert cfg.vpn_enabled is True
    assert calls == ["stop", "start"]
    body = res.json()
    assert body.get("status") == "restarted"
    assert body.get("started_apps") == ["prowlarr"]


def test_settings_vpn_switch_keeps_enabled_when_start_fails(tmp_path: Path, monkeypatch):
    from unittest.mock import AsyncMock

    client, cfg = _client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    monkeypatch.setattr(
        settings_api.vpn_manager,
        "start",
        lambda: {
            "status": "error",
            "detail": "VPN config missing: /config/vpn/wg0.conf",
            "tunnel_up": False,
            "enabled": True,
        },
    )
    monkeypatch.setattr(
        "core.integrations.lifecycle.stop_tunneled_apps",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "core.integrations.lifecycle.start_tunneled_apps",
        AsyncMock(return_value=[]),
    )

    res = client.patch("/api/settings", json={"vpn_enabled": True}, headers=headers)
    assert res.status_code == 200
    assert cfg.vpn_enabled is True
    notes = " ".join(res.json().get("notes") or [])
    assert "VPN start failed" in notes
    assert "cannot leak" in notes


def test_settings_reports_applied_vpn_and_homepage_keys(tmp_path: Path, monkeypatch):
    from core.crypto import SecretStore
    from core.integrations import credentials as credentials_mod

    client, cfg = _client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    store = SecretStore(cfg=cfg)
    monkeypatch.setattr(settings_api, "secret_store", store)
    monkeypatch.setattr(credentials_mod, "secret_store", store)

    empty = client.get("/api/settings", headers=headers)
    assert empty.status_code == 200
    body = empty.json()
    assert body["vpn"]["enabled"] is False
    assert body["homepage_keys"]["jellyfin"]["configured"] is False
    assert body["homepage_keys"]["seerr"]["configured"] is False
    assert body["homepage_keys"]["jellyfin"]["working"] is False

    saved = client.patch(
        "/api/settings",
        json={"jellyfin_api_key": "jf-test-key-abcdefghijklmnopqrstuvwxyz"},
        headers=headers,
    )
    assert saved.status_code == 200
    jelly = saved.json()["homepage_keys"]["jellyfin"]
    assert jelly["configured"] is True
    assert saved.json()["jellyfin_api_key_configured"] is True
    assert "Saved" in jelly["detail"] or jelly["working"] is True

    from unittest.mock import AsyncMock

    monkeypatch.setattr(
        settings_api.vpn_manager,
        "start",
        lambda: {"status": "started", "tunnel_up": True, "enabled": True},
    )
    monkeypatch.setattr("core.integrations.lifecycle.stop_tunneled_apps", AsyncMock(return_value=[]))
    monkeypatch.setattr("core.integrations.lifecycle.start_tunneled_apps", AsyncMock(return_value=[]))
    on = client.patch("/api/settings", json={"vpn_enabled": True}, headers=headers)
    assert on.status_code == 200
    assert on.json()["vpn"]["enabled"] is True
    again = client.get("/api/settings", headers=headers)
    assert again.json()["vpn"]["enabled"] is True
    assert again.json()["homepage_keys"]["jellyfin"]["configured"] is True
