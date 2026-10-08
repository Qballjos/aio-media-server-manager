"""Branding title and custom image uploads."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from api.app import create_app
from api.routers import branding as branding_api
from api.routers import settings as settings_api
from core.auth import auth_manager
from core.settings import Settings
from core import settings as settings_mod


# Valid 1x1 PNG (real file bytes)
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
    monkeypatch.setattr(branding_api, "branding_mod", __import__("core.branding", fromlist=["*"]))
    # Ensure branding module uses the test settings singleton
    import core.branding as branding_mod

    monkeypatch.setattr(branding_mod, "settings", test_settings)
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


def test_public_branding_defaults(tmp_path: Path, monkeypatch):
    client, _cfg = _client(tmp_path, monkeypatch)
    res = client.get("/api/branding")
    assert res.status_code == 200
    data = res.json()
    assert data["title"] == "AIO Media Server Manager"
    assert data["login_message"] == ""
    assert data["accent_color"] == "#f97316"
    assert data["header_url"].endswith("logo-aio-media-manager.png")
    assert data["slots"]["favicon"]["recommended"]


def test_brand_title_and_image_upload(tmp_path: Path, monkeypatch):
    client, cfg = _client(tmp_path, monkeypatch)
    headers = _auth_headers(client)

    patched = client.patch("/api/branding", json={"title": "Homelab Media"}, headers=headers)
    assert patched.status_code == 200
    assert patched.json()["title"] == "Homelab Media"

    accent = client.patch("/api/branding", json={"accent_color": "#3b82f6"}, headers=headers)
    assert accent.status_code == 200
    assert accent.json()["accent_color"] == "#3b82f6"
    assert accent.json()["accent_custom"] is True

    reset_accent = client.patch("/api/branding", json={"accent_color": "default"}, headers=headers)
    assert reset_accent.status_code == 200
    assert reset_accent.json()["accent_color"] == "#f97316"

    message = client.patch(
        "/api/branding",
        json={"login_message": "  Welcome home.\nThe kettle is on.  "},
        headers=headers,
    )
    assert message.status_code == 200
    assert message.json()["login_message"] == "Welcome home.\nThe kettle is on."
    public = client.get("/api/branding")
    assert public.json()["login_message"] == "Welcome home.\nThe kettle is on."

    cleared_message = client.patch("/api/branding", json={"login_message": "   "}, headers=headers)
    assert cleared_message.status_code == 200
    assert cleared_message.json()["login_message"] == ""

    uploaded = client.put(
        "/api/branding/header",
        content=_MIN_PNG,
        headers={**headers, "Content-Type": "image/png"},
    )
    assert uploaded.status_code == 200, uploaded.text
    body = uploaded.json()
    assert body["slots"]["header"]["custom"] is True
    assert body["header_url"].startswith("/api/branding/file/header")

    file_res = client.get(body["header_url"].split("?")[0])
    assert file_res.status_code == 200
    assert file_res.content[:8] == b"\x89PNG\r\n\x1a\n"

    settings_res = client.get("/api/settings", headers=headers)
    assert settings_res.status_code == 200
    assert settings_res.json()["branding"]["title"] == "Homelab Media"

    assert (cfg.config_dir / "branding" / "header.png").is_file()

    cleared = client.delete("/api/branding/header", headers=headers)
    assert cleared.status_code == 200
    assert cleared.json()["slots"]["header"]["custom"] is False


def test_branding_rejects_bad_payload(tmp_path: Path, monkeypatch):
    client, _cfg = _client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    bad = client.put(
        "/api/branding/logo",
        content=b"not-an-image",
        headers={**headers, "Content-Type": "application/octet-stream"},
    )
    assert bad.status_code == 422
