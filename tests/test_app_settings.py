from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from applications.catalog import ApplicationCatalog, refresh_live_catalogs
from core.app_prefs import AppPrefsError, load_app_ports, update_app_prefs, validate_port
from core.settings import Settings, settings


def test_validate_port_bounds():
    assert validate_port(8989) == 8989
    with pytest.raises(AppPrefsError):
        validate_port(80)
    with pytest.raises(AppPrefsError):
        validate_port(8080, reserved={8080})


def test_prefs_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    cfg = Settings(
        config_dir=tmp_path / "config",
        download_dir=tmp_path / "downloads",
        media_dir=tmp_path / "media",
        install_dir=tmp_path / "apps",
    )
    cfg.initialise()
    update_app_prefs(
        "sonarr",
        port=18989,
        autostart=False,
        reserved_ports={cfg.api_port},
        app_settings=cfg,
    )
    assert load_app_ports(cfg)["sonarr"] == 18989
    catalog = ApplicationCatalog(app_settings=cfg)
    assert catalog.get("sonarr").port == 18989


def test_patch_application_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    cfg = Settings(
        config_dir=tmp_path / "config",
        download_dir=tmp_path / "downloads",
        media_dir=tmp_path / "media",
        install_dir=tmp_path / "apps",
    )
    cfg.initialise()
    monkeypatch.setattr(settings, "config_dir", cfg.config_dir)
    from api.routers import applications as apps_mod
    from api.routers import catalog as cat_mod

    apps_mod.catalog._settings = settings
    cat_mod.catalog._settings = settings
    refresh_live_catalogs()

    client = TestClient(create_app())
    resp = client.get("/api/applications/sonarr/settings")
    assert resp.status_code == 200
    assert resp.json()["default_port"] == 8989

    resp = client.patch(
        "/api/applications/sonarr/settings",
        json={"port": 18989, "autostart": False, "restart": False},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["port"] == 18989
    assert resp.json()["autostart"] is False

    resp = client.get("/api/catalog/sonarr")
    assert resp.json()["port"] == 18989

    resp = client.patch(
        "/api/applications/sonarr/settings",
        json={"port": 7878},
    )
    assert resp.status_code == 409
