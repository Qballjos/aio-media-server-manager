from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from core.auth import AuthManager
from core.settings import Settings
from core.tv_devices import TvDevices


def request(token, path="/api/homepage", method="GET", query=b""):
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
    store = TvDevices(tmp_path)
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
        TvDevices(tmp_path).authenticate(request(token), token)
        == "tv:" + connection["deviceId"]
    )
    with pytest.raises(HTTPException):
        store.claim(invitation["pairingCode"], "Again")
    store.revoke(connection["deviceId"])
    with pytest.raises(HTTPException) as error:
        store.authenticate(request(token), token)
    assert error.value.status_code == 401


def test_new_and_expired_invitations(tmp_path, monkeypatch):
    store = TvDevices(tmp_path)
    old = store.invite()
    current = store.invite()
    with pytest.raises(HTTPException):
        store.claim(old["pairingCode"], "Old")
    monkeypatch.setattr("core.tv_devices.time.time", lambda: 10**12)
    with pytest.raises(HTTPException):
        store.claim(current["pairingCode"], "Expired")


def test_concurrent_claims_issue_only_one_device(tmp_path):
    store = TvDevices(tmp_path)
    code = store.invite()["pairingCode"]

    def claim(_):
        try:
            return store.claim(code, "TV")
        except HTTPException:
            return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(result is not None for result in pool.map(claim, range(8))) == 1
    assert len(store.devices()) == 1


def test_device_cannot_use_admin_endpoints_or_download_search(tmp_path):
    manager = AuthManager(Settings(config_dir=tmp_path))
    connection = manager.tv_devices.claim(
        manager.tv_devices.invite()["pairingCode"], "TV"
    )
    token = connection["accessToken"]
    for path in ["/api/homepage", "/api/homepage/resume", "/api/homepage/art"]:
        assert manager.authenticate_request(request(token, path)).startswith("tv:")
    for path, method in [
        ("/api/settings", "GET"),
        ("/api/tv/pairings", "POST"),
        ("/api/tv/devices", "GET"),
        ("/api/homepage/grab", "POST"),
    ]:
        with pytest.raises(HTTPException) as error:
            manager.authenticate_request(request(token, path, method))
        assert error.value.status_code == 403
    with pytest.raises(HTTPException):
        manager.authenticate_request(
            request(token, "/api/homepage/search", query=b"provider=prowlarr")
        )


def test_router_requires_admin_then_claims_and_disconnects(tmp_path, monkeypatch):
    from api.routers import tv

    manager = AuthManager(Settings(config_dir=tmp_path))
    manager.create_admin("admin", "a-test-password", email="test@example.invalid")
    monkeypatch.setattr(tv, "auth_manager", manager)
    app = FastAPI()
    app.include_router(tv.router)
    client = TestClient(app)
    assert client.post("/api/tv/pairings").status_code == 401
    headers = {"Authorization": "Bearer " + manager.issue_token("admin")}
    invitation = client.post("/api/tv/pairings", headers=headers).json()
    connection = client.post(
        "/api/tv/pairings/claim",
        json={"code": invitation["pairingCode"], "deviceName": "TV"},
    ).json()
    tv_headers = {"Authorization": "Bearer " + connection["accessToken"]}
    assert client.get("/api/tv/devices", headers=tv_headers).status_code == 403
    assert len(client.get("/api/tv/devices", headers=headers).json()["devices"]) == 1
    assert client.post("/api/tv/disconnect", headers=tv_headers).status_code == 200
    assert client.post("/api/tv/disconnect", headers=tv_headers).status_code == 401


def test_tv_home_does_not_reconfigure_seerr_or_override_library_settings(
    tmp_path, monkeypatch
):
    from api.routers import homepage

    manager = AuthManager(Settings(config_dir=tmp_path))
    manager.create_admin("admin", "a-test-password", email="test@example.invalid")
    monkeypatch.setattr(homepage, "auth_manager", manager)
    connection = manager.tv_devices.claim(
        manager.tv_devices.invite()["pairingCode"], "TV"
    )
    monkeypatch.setattr(homepage, "homepage_snapshot", lambda *a, **k: {"trending": []})

    def must_not_reconfigure(*args):
        raise AssertionError("TV must not reconfigure Seerr links")

    monkeypatch.setattr(homepage, "sync_seerr_external_links", must_not_reconfigure)
    requested = []
    monkeypatch.setattr(
        homepage,
        "homepage_request",
        lambda body: requested.append(body) or {"ok": True},
    )
    app = FastAPI()
    app.include_router(homepage.router)
    client = TestClient(app)
    headers = {"Authorization": "Bearer " + connection["accessToken"]}
    assert client.get("/api/homepage", headers=headers).status_code == 200
    assert (
        client.post(
            "/api/homepage/request",
            headers=headers,
            json={
                "mediaType": "movie",
                "mediaId": 123,
                "rootFolder": "/private",
                "profileId": 9,
            },
        ).status_code
        == 200
    )
    assert requested == [{"mediaType": "movie", "mediaId": 123, "seasons": None}]


def test_continue_watching_uses_stored_key_and_filters_sensitive_fields(
    tmp_path, monkeypatch
):
    from types import SimpleNamespace
    from core import homepage

    catalog = SimpleNamespace(
        has=lambda n: True, get=lambda n: SimpleNamespace(port=8096)
    )
    monkeypatch.setattr(homepage, "ApplicationCatalog", lambda: catalog)
    monkeypatch.setattr(homepage, "_running_names", lambda: {"jellyfin"})
    monkeypatch.setattr(
        homepage.secret_store, "get_secret", lambda n: "server-only-key"
    )
    calls = []

    def fetch(url, **kwargs):
        calls.append(url)
        if url.endswith("/Users"):
            return [{"Id": "a" * 32}], None
        return {
            "Items": [
                {
                    "Id": "b" * 32,
                    "Name": "Movie",
                    "Type": "Movie",
                    "Path": "/private/media",
                    "Token": "never-return",
                }
            ]
        }, None

    monkeypatch.setattr(homepage, "_fetch_json", fetch)
    result = homepage.homepage_resume()
    assert result == {"items": [{"Id": "b" * 32, "Name": "Movie", "Type": "Movie"}]}
    assert len(calls) == 3
    monkeypatch.setattr(homepage.secret_store, "get_secret", lambda n: None)
    assert homepage.homepage_resume() == {"items": []}
    assert len(calls) == 3
