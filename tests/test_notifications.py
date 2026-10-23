"""Settings → Notifications: validation, secrets, the test endpoint and the change watcher."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

import core.notifications as notifications
from api.app import create_app
from core.auth import auth_manager
from core.crypto import SecretStore
from core.settings import Settings
from core import settings as settings_mod

WEBHOOK = "https://discord.com/api/webhooks/123456/abcDEF_-xyz"


def _client(tmp_path: Path, monkeypatch) -> TestClient:
    cfg = Settings(
        config_dir=tmp_path / "config",
        download_dir=tmp_path / "downloads",
        media_dir=tmp_path / "media",
        install_dir=tmp_path / "apps",
    )
    cfg.initialise()
    monkeypatch.setattr(auth_manager, "_settings", cfg)
    monkeypatch.setattr(settings_mod, "settings", cfg)
    monkeypatch.setattr(notifications, "settings", cfg)
    monkeypatch.setattr(notifications, "secret_store", SecretStore(cfg=cfg))
    auth_manager._rate._hits.clear()
    return TestClient(create_app())


def _headers(client: TestClient) -> dict[str, str]:
    setup = client.post(
        "/api/auth/setup",
        json={"username": "admin", "email": "admin@example.com", "password": "StrongPassword123!"},
    )
    assert setup.status_code == 200
    return {"Authorization": f"Bearer {setup.json()['access_token']}"}


def test_settings_keep_secrets_out_of_responses_and_validate(tmp_path: Path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    assert client.get("/api/notifications").status_code == 401
    headers = _headers(client)

    body = client.get("/api/notifications", headers=headers).json()
    assert body["discord"] == {"enabled": False, "webhook_saved": False}
    assert set(body["events"]) == set(notifications.EVENTS)

    # Only Discord webhooks are accepted (no requests to other hosts).
    bad = client.put("/api/notifications", json={"discord": {"enabled": True, "webhook_url": "http://192.168.1.5/hook"}}, headers=headers)
    assert bad.status_code == 422
    # E-mail needs a server and recipients before it can be switched on.
    assert client.put("/api/notifications", json={"email": {"enabled": True}}, headers=headers).status_code == 422
    assert client.put(
        "/api/notifications",
        json={"email": {"enabled": True, "host": "smtp.example.com", "recipients": "me@example.com, not-an-address"}},
        headers=headers,
    ).status_code == 422

    saved = client.put(
        "/api/notifications",
        json={
            "discord": {"enabled": True, "webhook_url": WEBHOOK},
            "email": {
                "enabled": True,
                "host": "smtp.example.com",
                "port": 465,
                "security": "ssl",
                "username": "me@example.com",
                "password": "s3cret",
                "recipients": "me@example.com; you@example.com",
            },
            "events": {"disk": False},
        },
        headers=headers,
    )
    assert saved.status_code == 200, saved.text
    data = saved.json()
    assert data["discord"]["webhook_saved"] and data["email"]["password_saved"]
    assert data["email"]["recipients"] == ["me@example.com", "you@example.com"]
    assert data["events"]["disk"] is False and data["events"]["apps"] is True
    assert WEBHOOK not in saved.text and "s3cret" not in saved.text

    # Saving again without secrets keeps them; an empty string removes them.
    again = client.put("/api/notifications", json={"discord": {"enabled": False}, "email": {"password": ""}}, headers=headers).json()
    assert again["discord"]["webhook_saved"] is True
    assert again["email"]["password_saved"] is False


def test_test_endpoint_reports_send_errors(tmp_path: Path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    headers = _headers(client)
    res = client.post("/api/notifications/test", json={"channel": "discord"}, headers=headers)
    assert res.status_code == 422 and "No Discord webhook" in res.json()["detail"]

    sent = {}
    client.put("/api/notifications", json={"discord": {"enabled": True, "webhook_url": WEBHOOK}}, headers=headers)

    class _Res:
        status_code = 204

    def fake_post(url, json, timeout, allow_redirects):
        sent.update(url=url, payload=json)
        return _Res()

    monkeypatch.setattr(notifications.requests, "post", fake_post)
    assert client.post("/api/notifications/test", json={"channel": "discord"}, headers=headers).status_code == 200
    assert sent["url"] == WEBHOOK and sent["payload"]["embeds"][0]["title"] == "Test notification"


def test_watcher_reports_changes_once_and_recoveries():
    watcher = notifications.Watcher(notified_updates=["Sonarr 4.1"])
    base = {"sick_apps": {}, "vpn_up": True, "tunnel_up": None, "updates": ["Sonarr 4.1"], "full_disks": {"media": 50.0}}
    assert watcher.messages(base) == []

    sick = dict(base, sick_apps={"sonarr": "crash_loop"})
    msgs = watcher.messages(sick)
    assert [(m[0], m[1]) for m in msgs] == [("apps", "sonarr keeps crashing")]
    assert watcher.messages(sick) == []  # not repeated
    assert [m[1] for m in watcher.messages(base)] == ["sonarr is running again"]

    # The VPN must be down for two checks before it is reported, and once only.
    down = dict(base, vpn_up=False)
    assert watcher.messages(down) == []
    assert [m[1] for m in watcher.messages(down)] == ["VPN is down"]
    assert watcher.messages(down) == []
    assert [m[1] for m in watcher.messages(base)] == ["VPN is back"]

    # New updates once; a disk over 90% once until it drops below 85%.
    more = dict(base, updates=["Radarr 6.5", "Sonarr 4.1"], full_disks={"media": 93.0})
    titles = [m[1] for m in watcher.messages(more)]
    assert titles == ["Updates available", "media storage is 93% full"]
    assert watcher.messages(more) == []
    assert watcher.messages(dict(more, full_disks={"media": 87.0})) == []
    watcher.messages(dict(more, full_disks={"media": 80.0}))
    assert [m[1] for m in watcher.messages(dict(more, full_disks={"media": 95.0}))] == ["media storage is 95% full"]


def test_notify_skips_switched_off_events_and_never_raises(tmp_path: Path, monkeypatch):
    cfg = Settings(config_dir=tmp_path / "config", download_dir=tmp_path / "d", media_dir=tmp_path / "m", install_dir=tmp_path / "a")
    cfg.initialise()
    monkeypatch.setattr(notifications, "settings", cfg)
    store = SecretStore(cfg=cfg)
    monkeypatch.setattr(notifications, "secret_store", store)
    notifications.save_config(discord_enabled=True, webhook_url=WEBHOOK, email={}, smtp_password=None, events={"disk": False})

    calls = []
    monkeypatch.setattr(notifications, "send_discord", lambda *a: calls.append(a) or (_ for _ in ()).throw(RuntimeError("down")))
    assert notifications.notify("disk", "x", "y") == []
    assert calls == []
    assert notifications.notify("apps", "x", "y") == ["Discord: down"]
