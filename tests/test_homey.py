from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from core.auth import AuthManager
from core.settings import Settings
from core.homey_connections import HomeyConnections


def request(token, path="/api/homey/dashboard", method="GET", query=b""):
    return Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "query_string": query,
            "headers": [(b"authorization", f"Bearer {token}".encode())],
            "scheme": "https",
            "server": ("test", 443),
        }
    )


def test_pairing_is_one_use_private_persistent_and_revocable(tmp_path):
    store = HomeyConnections(tmp_path)
    invitation = store.invite()
    connection = store.claim(invitation["pairingCode"], "Living room")
    token = connection["accessToken"]
    assert (
        token not in store.path.read_text()
        and invitation["pairingCode"] not in store.path.read_text()
    )
    assert store.path.stat().st_mode & 0o777 == 0o600
    assert set(store.devices()[0]) == {"id", "name", "created"}
    assert (
        HomeyConnections(tmp_path).authenticate(request(token), token)
        == "homey:" + connection["deviceId"]
    )
    with pytest.raises(HTTPException):
        store.claim(invitation["pairingCode"], "Again")
    store.revoke(connection["deviceId"])
    with pytest.raises(HTTPException) as error:
        store.authenticate(request(token), token)
    assert error.value.status_code == 401


def test_new_and_expired_invitations(tmp_path, monkeypatch):
    store = HomeyConnections(tmp_path)
    old = store.invite()
    current = store.invite()
    with pytest.raises(HTTPException):
        store.claim(old["pairingCode"], "Old")
    monkeypatch.setattr("core.homey_connections.time.time", lambda: 10**12)
    with pytest.raises(HTTPException):
        store.claim(current["pairingCode"], "Expired")


def test_concurrent_claims_issue_only_one_device(tmp_path):
    store = HomeyConnections(tmp_path)
    code = store.invite()["pairingCode"]

    def claim(_):
        try:
            return store.claim(code, "TV")
        except HTTPException:
            return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(result is not None for result in pool.map(claim, range(8))) == 1
    assert len(store.devices()) == 1


def test_read_only_scope_and_router_authentication(tmp_path, monkeypatch):
    from api.routers import homey

    manager = AuthManager(Settings(config_dir=tmp_path))
    manager.create_admin("admin", "a-test-password", email="test@example.invalid")
    monkeypatch.setattr(homey, "auth_manager", manager)
    reads = []
    monkeypatch.setattr(
        homey, "dashboard", lambda: reads.append(True) or {"schemaVersion": 1}
    )
    app = FastAPI()
    app.include_router(homey.router)
    client = TestClient(app)
    assert client.get("/api/homey/dashboard").status_code == 401
    assert client.post("/api/homey/pairings").status_code == 401
    assert reads == []
    admin = {"Authorization": "Bearer " + manager.issue_token("admin")}
    invitation = client.post("/api/homey/pairings", headers=admin)
    assert invitation.headers["cache-control"] == "no-store"
    claimed = client.post(
        "/api/homey/pairings/claim", json={"code": invitation.json()["pairingCode"]}
    )
    assert claimed.status_code == 200
    assert claimed.headers["cache-control"] == "no-store"
    token = claimed.json()["accessToken"]
    assert token.startswith("homey_")
    headers = {"Authorization": "Bearer " + token}
    reply = client.get("/api/homey/dashboard", headers=headers)
    assert reply.status_code == 200 and reads == [True]
    assert reply.headers["cache-control"] == "no-store"
    for path, method in [
        ("/api/settings", "GET"),
        ("/api/homepage", "GET"),
        ("/api/homepage/request", "POST"),
        ("/api/homey/pairings", "POST"),
        ("/api/homey/devices", "GET"),
        ("/api/tv/devices", "GET"),
    ]:
        with pytest.raises(HTTPException) as error:
            manager.authenticate_request(request(token, path, method))
        assert error.value.status_code == 403
    assert client.get("/api/homey/devices", headers=headers).status_code == 403
    device_id = claimed.json()["deviceId"]
    assert token not in str(client.get("/api/homey/devices", headers=admin).json())
    assert (
        client.delete("/api/homey/devices/" + device_id, headers=headers).status_code
        == 403
    )
    assert (
        client.delete("/api/homey/devices/" + device_id, headers=admin).status_code
        == 200
    )
    assert client.get("/api/homey/dashboard", headers=headers).status_code == 401
    assert reads == [True]
    # TV and Homey credentials remain isolated, even though both use Bearer.
    tv = manager.tv_devices.claim(manager.tv_devices.invite()["pairingCode"], "TV")
    assert (
        client.get(
            "/api/homey/dashboard",
            headers={"Authorization": "Bearer " + tv["accessToken"]},
        ).status_code
        == 403
    )


def test_projection_cache_and_independent_source_errors(monkeypatch):
    from core import homey_dashboard as hd

    monkeypatch.setattr(hd, "_cache", None)
    calls = []
    monkeypatch.setattr(
        hd,
        "now_playing",
        lambda *a, **k: calls.append(1)
        or [
            {
                "title": "Film",
                "source": "plex",
                "progress": 150,
                "paused": True,
                "user": "private",
                "url": "secret",
                "poster": "secret",
            }
        ],
    )
    monkeypatch.setattr(hd, "recent", lambda: [{"title": "New"}])
    first = hd.dashboard()
    assert hd.dashboard() == first and len(calls) == 1
    assert first["playing"]["items"] == [
        {
            "title": "Film",
            "detail": "",
            "source": "plex",
            "progress": 100,
            "paused": True,
        }
    ]
    assert "private" not in str(first) and "secret" not in str(first)
    monkeypatch.setattr(hd, "_expires", 0)

    def fail():
        raise RuntimeError("private error")

    monkeypatch.setattr(hd, "recent", fail)
    second = hd.dashboard()
    assert second["recent"] == {"state": "unavailable", "items": []}
    assert second["playing"]["state"] == "ready"
    assert "private error" not in str(second)


def test_recent_newest_first_and_no_links_or_credentials(monkeypatch):
    from core import homey_dashboard as hd

    monkeypatch.setattr(hd, "ApplicationCatalog", lambda: None)
    monkeypatch.setattr(hd, "_running_names", lambda: set())
    monkeypatch.setattr(
        hd,
        "_collect_jellyfin_recent",
        lambda *a, **k: [{"title": "Old", "when": "2025-01-01", "poster": "secret"}],
    )
    monkeypatch.setattr(
        hd,
        "_collect_plex_recent",
        lambda *a, **k: [{"title": "New", "when": "2026-01-01", "url": "secret"}],
    )
    rows = hd.recent()
    assert [r["title"] for r in rows] == ["New", "Old"]
    assert all(set(r) == {"title", "detail", "source", "addedAt"} for r in rows)


def test_homey_recent_never_discovers_or_modifies_jellyfin_credentials(
    tmp_path, monkeypatch
):
    from types import SimpleNamespace
    from core import homepage

    plugin = SimpleNamespace(config_dir=tmp_path, is_installed=lambda: True)
    catalog = SimpleNamespace(
        has=lambda name: name == "jellyfin", get=lambda name: plugin
    )
    calls = []
    monkeypatch.setattr(homepage.secret_store, "get_secret", lambda name: None)
    monkeypatch.setattr(
        homepage, "get_application_api_key", lambda *a: calls.append(True)
    )
    notes = []
    assert (
        homepage._collect_jellyfin_recent(
            catalog, {"jellyfin"}, notes, "nas", read_only=True
        )
        == []
    )
    assert calls == [] and notes[0]["state"] == "error"


def test_strict_playing_read_reports_missing_key_without_discovery(
    tmp_path, monkeypatch
):
    from types import SimpleNamespace
    from core import homepage_status as hs

    plugin = SimpleNamespace(is_installed=lambda: True)
    catalog = SimpleNamespace(
        has=lambda name: name == "jellyfin", get=lambda name: plugin
    )
    monkeypatch.setattr(hs, "ApplicationCatalog", lambda: catalog)
    monkeypatch.setattr(hs, "_running_names", lambda: {"jellyfin"})
    monkeypatch.setattr(hs.secret_store, "get_secret", lambda name: None)
    with pytest.raises(RuntimeError, match="unavailable"):
        hs.now_playing("nas", strict=True)
    assert hs.now_playing("nas") == []
