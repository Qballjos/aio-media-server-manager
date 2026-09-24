"""TRaSH Recyclarr config, prefs, and API."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from api.app import create_app
from applications.catalog import ApplicationCatalog
from core.auth import auth_manager
from core.recyclarr import (
    MANAGED_MARK,
    default_prefs,
    load_prefs,
    save_yaml,
    write_recyclarr_config,
)
from core.settings import Settings


def _settings(tmp_path: Path) -> Settings:
    cfg = Settings(
        config_dir=tmp_path / "config",
        download_dir=tmp_path / "downloads",
        media_dir=tmp_path / "media",
        install_dir=tmp_path / "apps",
    )
    cfg.initialise()
    return cfg


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
    return {"Authorization": f"Bearer {setup.json()['access_token']}"}


def test_default_yaml_matches_trash_hd_templates(tmp_path: Path):
    path = write_recyclarr_config(
        tmp_path / "recyclarr",
        sonarr_url="http://127.0.0.1:8989",
        sonarr_key="sonarr-key",
        radarr_url="http://127.0.0.1:7878",
        radarr_key="radarr-key",
    )
    text = path.read_text(encoding="utf-8")
    assert MANAGED_MARK in text
    assert "web-1080p:" in text
    assert "sonarr-anime-remux-1080p:" in text
    assert "hd-bluray-web:" in text
    assert "web-2160p:" not in text
    assert "uhd-bluray-web:" not in text
    assert "158188097a58d7687dee647e04af0da3" in text
    assert "f8bf8eab4617f12dfdbd16303d8da245" in text
    assert "delete_old_custom_formats: true" in text
    prefs = load_prefs(tmp_path / "recyclarr")
    assert prefs["sonarr_web_1080p"] is True
    assert prefs["radarr_uhd"] is False
    assert prefs["user_edited"] is False


def test_uhd_opt_in_and_jellyfin_naming(tmp_path: Path):
    prefs = default_prefs()
    prefs.update({"sonarr_web_2160p": True, "radarr_uhd": True, "naming": "jellyfin"})
    path = write_recyclarr_config(
        tmp_path / "recyclarr",
        sonarr_url="http://127.0.0.1:8989",
        sonarr_key="s",
        radarr_url="http://127.0.0.1:7878",
        radarr_key="r",
        prefs=prefs,
        force=True,
    )
    text = path.read_text(encoding="utf-8")
    assert "web-2160p:" in text
    assert "uhd-bluray-web:" in text
    assert "e3f37512790f00d0e89e54fe5e790d1c" in text
    assert "ff204bbcecdd487d1cefcefdbf0c278d" in text
    assert "jellyfin-tv" in text
    assert "jellyfin-tmdb" in text


def test_user_edited_yaml_is_preserved(tmp_path: Path):
    root = tmp_path / "recyclarr"
    path = write_recyclarr_config(
        root,
        sonarr_url="http://127.0.0.1:8989",
        sonarr_key="old",
        radarr_url="http://127.0.0.1:7878",
        radarr_key="old",
    )
    save_yaml(root, "sonarr:\n  custom:\n    base_url: http://old\n    api_key: keepme\n    trash_id: abc\n")
    write_recyclarr_config(
        root,
        sonarr_url="http://127.0.0.1:8989",
        sonarr_key="new-key",
        radarr_url="http://127.0.0.1:7878",
        radarr_key="r",
        force=False,
    )
    text = path.read_text(encoding="utf-8")
    assert "custom:" in text
    assert "api_key: new-key" in text
    assert load_prefs(root)["user_edited"] is True


def test_recyclarr_api_prefs_and_yaml(tmp_path: Path, monkeypatch):
    cfg = _settings(tmp_path)
    catalog = ApplicationCatalog(app_settings=cfg)
    monkeypatch.setattr("core.recyclarr.ApplicationCatalog", lambda: catalog)
    monkeypatch.setattr("core.recyclarr.get_application_api_key", lambda _name: "test-key")
    monkeypatch.setattr(auth_manager, "_settings", cfg)

    client = TestClient(create_app())
    headers = _auth_headers(client)

    patched = client.patch(
        "/api/recyclarr",
        json={"sonarr_web_2160p": True, "naming": "plex"},
        headers=headers,
    )
    assert patched.status_code == 200
    body = patched.json()
    assert "web-2160p:" in body["yaml"]
    assert body["prefs"]["sonarr_web_2160p"] is True

    saved = client.put("/api/recyclarr", json={"yaml": "sonarr:\n  hand-edit: true\n"}, headers=headers)
    assert saved.status_code == 200
    assert "hand-edit: true" in saved.json()["yaml"]
    assert saved.json()["user_edited"] is True

    reset = client.post("/api/recyclarr/reset", headers=headers)
    assert reset.status_code == 200
    assert reset.json()["user_edited"] is False
    assert "web-1080p:" in reset.json()["yaml"]


def test_recyclarr_sync_runs_once(tmp_path: Path, monkeypatch):
    cfg = _settings(tmp_path)
    catalog = ApplicationCatalog(app_settings=cfg)
    plugin = catalog.get("recyclarr")
    plugin.install_dir.mkdir(parents=True, exist_ok=True)
    (plugin.install_dir / "recyclarr").write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setattr("core.recyclarr.ApplicationCatalog", lambda: catalog)
    monkeypatch.setattr("core.recyclarr.get_application_api_key", lambda _name: "k")
    monkeypatch.setattr(auth_manager, "_settings", cfg)

    completed = MagicMock(returncode=0, stdout="sync ok", stderr="")
    with patch("core.recyclarr.subprocess.run", return_value=completed) as mock_run:
        client = TestClient(create_app())
        headers = _auth_headers(client)
        res = client.post("/api/recyclarr/sync", headers=headers)
    assert res.status_code == 200
    assert res.json()["ok"] is True
    assert mock_run.called
    assert "sync" in mock_run.call_args.args[0]
