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


def test_visual_preferences_persist_on_profile(tmp_path: Path, monkeypatch):
    client, cfg = _client(tmp_path, monkeypatch)
    headers = _auth_headers(client)

    me = client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["theme"] == "dark"
    assert me.json()["wallpaper"] == "default"
    assert me.json()["has_wallpaper_image"] is False
    assert me.json()["homepage_widget_debug"] is False

    patched = client.patch(
        "/api/auth/visuals",
        json={"theme": "light", "wallpaper": "jellyfin"},
        headers=headers,
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["theme"] == "light"
    assert patched.json()["wallpaper"] == "jellyfin"

    debug_on = client.patch(
        "/api/auth/visuals",
        json={"homepage_widget_debug": True},
        headers=headers,
    )
    assert debug_on.status_code == 200, debug_on.text
    assert debug_on.json()["homepage_widget_debug"] is True
    assert debug_on.json()["theme"] == "light"

    status = client.get("/api/auth/status")
    assert status.status_code == 200
    body = status.json()
    assert body["authenticated"] is True
    assert body["theme"] == "light"
    assert body["wallpaper"] == "jellyfin"
    assert body["homepage_widget_debug"] is True

    meta = (cfg.config_dir / "profile" / "profile.json").read_text(encoding="utf-8")
    assert '"theme": "light"' in meta
    assert '"wallpaper": "jellyfin"' in meta
    assert '"homepage_widget_debug": true' in meta

    uploaded = client.put(
        "/api/auth/wallpaper",
        content=_MIN_PNG,
        headers={**headers, "Content-Type": "image/png"},
    )
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()["wallpaper"] == "personal"
    assert uploaded.json()["has_wallpaper_image"] is True
    assert uploaded.json()["wallpaper_url"].startswith("/api/auth/wallpaper?")
    assert (cfg.config_dir / "profile" / "wallpaper.png").is_file()

    file_res = client.get("/api/auth/wallpaper", headers=headers)
    assert file_res.status_code == 200
    assert file_res.content[:8] == b"\x89PNG\r\n\x1a\n"

    cleared = client.delete("/api/auth/wallpaper", headers=headers)
    assert cleared.status_code == 200
    assert cleared.json()["has_wallpaper_image"] is False
    assert cleared.json()["wallpaper"] == "default"



def test_home_layout_is_kept_on_the_profile(tmp_path: Path, monkeypatch):
    client, cfg = _client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    assert client.get("/api/auth/me", headers=headers).json()["homepage_layout"] == []

    saved = client.patch(
        "/api/auth/visuals",
        json={"homepage_layout": ["downloads", "apps", "downloads", " search "]},
        headers=headers,
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["homepage_layout"] == ["downloads", "apps", "search"]
    assert client.get("/api/auth/status").json()["homepage_layout"] == ["downloads", "apps", "search"]
    # Saving the layout leaves the other visuals alone.
    assert client.get("/api/auth/me", headers=headers).json()["theme"] == "dark"


def test_glass_tuning_and_hidden_blocks_are_kept_on_the_profile(tmp_path: Path, monkeypatch):
    client, cfg = _client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    me = client.get("/api/auth/me", headers=headers).json()
    assert (me["glass_alpha"], me["glass_blur"], me["glass_depth"], me["wallpaper_blur"], me["homepage_hidden"]) == (0.5, 28, 1.0, 12, [])

    saved = client.patch(
        "/api/auth/visuals",
        json={"glass_alpha": 0.33, "glass_blur": 40, "glass_depth": 1.5, "wallpaper_blur": 6, "homepage_hidden": ["trending"], "wallpaper": "ocean"},
        headers=headers,
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert (body["glass_alpha"], body["glass_blur"], body["glass_depth"], body["wallpaper_blur"]) == (0.33, 40, 1.5, 6)
    assert body["homepage_hidden"] == ["trending"] and body["wallpaper"] == "ocean"
    assert client.patch("/api/auth/visuals", json={"glass_blur": 500}, headers=headers).status_code == 422
    assert client.get("/api/auth/status").json()["glass_blur"] == 40

    # Card widths: a third, a half or the full row; anything else is dropped.
    sized = client.patch("/api/auth/visuals", json={"homepage_sizes": {"requests": 12, "calendar": 5, "downloads": "6"}}, headers=headers)
    assert sized.status_code == 200, sized.text
    assert sized.json()["homepage_sizes"] == {"requests": 12, "downloads": 6}
    assert client.get("/api/auth/status").json()["homepage_sizes"] == {"requests": 12, "downloads": 6}


def test_home_grid_is_kept_on_the_profile(tmp_path: Path, monkeypatch):
    client, cfg = _client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    assert client.get("/api/auth/me", headers=headers).json()["homepage_grid"] == {}

    saved = client.patch(
        "/api/auth/visuals",
        json={
            "homepage_grid": {
                "desktop": [
                    {"id": "search", "x": 0, "y": 0, "w": 12, "h": 2},
                    {"id": "recent", "x": 10, "y": 2, "w": 4, "h": 3},
                    {"id": "search", "x": 0, "y": 5, "w": 6, "h": 2},
                    {"id": "calendar", "x": "1", "y": 2, "w": 7, "h": 4},
                ],
                "phone": [{"id": "downloads", "x": 0, "y": 0, "w": 9, "h": 2}],
                "watch": [{"id": "search", "x": 0, "y": 0, "w": 1, "h": 1}],
            }
        },
        headers=headers,
    )
    assert saved.status_code == 200, saved.text
    # Past the right edge, a second copy of an id, a size that does not exist: dropped. Numeric strings count.
    assert saved.json()["homepage_grid"] == {
        "desktop": [
            {"id": "search", "x": 0, "y": 0, "w": 12, "h": 2},
            {"id": "calendar", "x": 1, "y": 2, "w": 7, "h": 4},
        ],
        "phone": [],
    }
    assert client.get("/api/auth/status").json()["homepage_grid"] == saved.json()["homepage_grid"]
    # The grid lives next to the old order, which stays as it was.
    assert client.get("/api/auth/me", headers=headers).json()["homepage_layout"] == []


def test_locale_is_saved_on_the_profile(tmp_path: Path, monkeypatch):
    client, cfg = _client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    assert client.get("/api/auth/me", headers=headers).json()["locale"] == ""

    saved = client.patch("/api/auth/visuals", json={"locale": "nl"}, headers=headers)
    assert saved.status_code == 200, saved.text
    assert saved.json()["locale"] == "nl"
    assert client.get("/api/auth/status").json()["locale"] == "nl"
    assert '"locale": "nl"' in (cfg.config_dir / "profile" / "profile.json").read_text(encoding="utf-8")

    rejected = client.patch("/api/auth/visuals", json={"locale": "es"}, headers=headers)
    assert rejected.status_code == 422
