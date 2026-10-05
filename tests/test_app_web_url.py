"""LAN vs public subdomain Open UI URL helpers."""

from __future__ import annotations

import json
from pathlib import Path

from applications.shelfmark_mirrors import sync_shelfmark_audiobook_library_url
from core.app_web_url import (
    app_web_ui_url,
    catalog_app_browser_url,
    derive_public_app_base_domain,
    grimmory_browser_url,
)
from core.public_hostnames import save_hostnames
from core.settings import Settings


def test_lan_uses_host_port():
    assert (
        app_web_ui_url(app_name="sonarr", port=8989, hostname="192.168.2.223", scheme="http")
        == "http://192.168.2.223:8989"
    )


def test_https_uses_app_subdomain():
    assert (
        app_web_ui_url(app_name="sonarr", port=8989, hostname="media.example.com", scheme="https")
        == "https://sonarr.example.com"
    )


def test_configured_base_domain_does_not_break_lan():
    assert (
        app_web_ui_url(
            app_name="jellyfin",
            port=8096,
            hostname="192.168.2.223",
            scheme="http",
            base_domain="example.com",
        )
        == "http://192.168.2.223:8096"
    )


def test_configured_base_domain_used_on_https():
    assert (
        app_web_ui_url(
            app_name="jellyfin",
            port=8096,
            hostname="media.example.com",
            scheme="https",
            base_domain="example.com",
        )
        == "https://jellyfin.example.com"
    )


def test_catalog_app_browser_url_prefers_public_subdomain(tmp_path: Path, monkeypatch):
    cfg = Settings(config_dir=tmp_path, public_app_base_domain="example.com")
    monkeypatch.setattr("core.app_web_url.settings", cfg)
    monkeypatch.setattr("core.public_hostnames.settings", cfg)
    save_hostnames(
        {"grimmory": {"subdomain": "books", "enabled": True}},
        app_settings=cfg,
    )
    assert catalog_app_browser_url("grimmory", port=6060) == "https://books.example.com"
    assert grimmory_browser_url(port=6060) == "https://books.example.com"


def test_catalog_app_browser_url_falls_back_to_localhost(tmp_path: Path, monkeypatch):
    cfg = Settings(config_dir=tmp_path, public_app_base_domain="")
    monkeypatch.setattr("core.app_web_url.settings", cfg)
    monkeypatch.setattr("core.public_hostnames.settings", cfg)
    assert catalog_app_browser_url("grimmory", port=6060) == "http://127.0.0.1:6060"


def test_sync_shelfmark_audiobook_library_url_updates_managed(tmp_path: Path, monkeypatch):
    cfg = Settings(config_dir=tmp_path, public_app_base_domain="example.com")
    monkeypatch.setattr("core.app_web_url.settings", cfg)
    monkeypatch.setattr("core.public_hostnames.settings", cfg)
    save_hostnames(
        {"grimmory": {"subdomain": "grimmory", "enabled": True}},
        app_settings=cfg,
    )
    shelf_cfg = tmp_path / "shelfmark"
    shelf_cfg.mkdir()
    settings_path = shelf_cfg / "settings.json"
    settings_path.write_text(
        '{"AUDIOBOOK_LIBRARY_URL": "http://127.0.0.1:6060"}\n',
        encoding="utf-8",
    )
    assert sync_shelfmark_audiobook_library_url(shelf_cfg, port=6060) is True
    data = json.loads(settings_path.read_text(encoding="utf-8"))
    assert data["AUDIOBOOK_LIBRARY_URL"] == "https://grimmory.example.com"


def test_sync_shelfmark_audiobook_library_url_preserves_custom(tmp_path: Path, monkeypatch):
    cfg = Settings(config_dir=tmp_path, public_app_base_domain="example.com")
    monkeypatch.setattr("core.app_web_url.settings", cfg)
    monkeypatch.setattr("core.public_hostnames.settings", cfg)
    save_hostnames(
        {"grimmory": {"subdomain": "grimmory", "enabled": True}},
        app_settings=cfg,
    )
    shelf_cfg = tmp_path / "shelfmark"
    shelf_cfg.mkdir()
    settings_path = shelf_cfg / "settings.json"
    settings_path.write_text(
        '{"AUDIOBOOK_LIBRARY_URL": "https://audiobooks.example.com"}\n',
        encoding="utf-8",
    )
    assert sync_shelfmark_audiobook_library_url(shelf_cfg, port=6060) is False
    data = json.loads(settings_path.read_text(encoding="utf-8"))
    assert data["AUDIOBOOK_LIBRARY_URL"] == "https://audiobooks.example.com"


def test_derive_public_app_base_domain():
    assert derive_public_app_base_domain("media.example.com") == "example.com"
    assert derive_public_app_base_domain("example.com") == "example.com"
    assert derive_public_app_base_domain("media.example.co.uk") == "example.co.uk"
    assert derive_public_app_base_domain("sonarr.media.example.co.uk") == "example.co.uk"
    assert derive_public_app_base_domain("app.example.com.au") == "example.com.au"
    assert derive_public_app_base_domain("example.co.uk") == "example.co.uk"
