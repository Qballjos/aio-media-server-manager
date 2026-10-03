"""Admin profile image upload and serving."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from api.app import create_app
from api.routers import settings as settings_api
from core.auth import auth_manager
from core.settings import Settings
from core import settings as settings_mod
from core import profile as profile_mod

# Valid 1x1 PNG
_MIN_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
)


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
    monkeypatch.setattr(profile_mod, "settings", test_settings)
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


def test_avatar_upload_status_and_remove(tmp_path: Path, monkeypatch):
    client, cfg = _client(tmp_path, monkeypatch)
    headers = _auth_headers(client)

    me = client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["has_avatar"] is False
    assert me.json()["avatar_url"] is None

    status = client.get("/api/auth/status")
    assert status.status_code == 200
    assert status.json()["avatar_url"] is None

    uploaded = client.put(
        "/api/auth/avatar",
        content=_MIN_PNG,
        headers={**headers, "Content-Type": "image/png"},
    )
    assert uploaded.status_code == 200, uploaded.text
    body = uploaded.json()
    assert body["has_avatar"] is True
    assert body["avatar_url"].startswith("/api/auth/avatar?")

    file_res = client.get("/api/auth/avatar", headers=headers)
    assert file_res.status_code == 200
    assert file_res.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert (cfg.config_dir / "profile" / "avatar.png").is_file()

    status2 = client.get("/api/auth/status")
    assert status2.json()["avatar_url"].startswith("/api/auth/avatar?")

    cleared = client.delete("/api/auth/avatar", headers=headers)
    assert cleared.status_code == 200
    assert cleared.json()["has_avatar"] is False
    assert cleared.json()["avatar_url"] is None
    assert client.get("/api/auth/avatar", headers=headers).status_code == 404


def test_avatar_rejects_bad_payload(tmp_path: Path, monkeypatch):
    client, _cfg = _client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    bad = client.put(
        "/api/auth/avatar",
        content=b"not-an-image",
        headers={**headers, "Content-Type": "application/octet-stream"},
    )
    assert bad.status_code == 422
