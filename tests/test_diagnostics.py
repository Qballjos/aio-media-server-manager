from pathlib import Path

from fastapi.testclient import TestClient

from api.app import create_app
from applications.catalog import ApplicationCatalog
from applications.sonarr import SonarrApp
from core.diagnostics import diagnostics
from core.settings import Settings, settings


def test_is_installed_when_metadata_exists(tmp_path: Path):
    app = SonarrApp(base_config_dir=tmp_path / "config", base_install_dir=tmp_path / "apps")
    app.install_dir.mkdir(parents=True)
    assert app.is_installed() is False
    (app.install_dir / ".amm_installed.json").write_text('{"version": "1.0"}', encoding="utf-8")
    assert app.is_installed() is True


def test_catalog_counts_available_vs_installed(tmp_path: Path):
    catalog = ApplicationCatalog(
        app_settings=Settings(
            config_dir=tmp_path / "config",
            install_dir=tmp_path / "apps",
        )
    )
    counts = catalog.counts()
    assert counts["catalog"] == len(catalog.names())
    assert counts["installed"] == 0
    assert counts["available"] == counts["catalog"]
    plugin = catalog.get("sonarr")
    plugin.install_dir.mkdir(parents=True)
    (plugin.install_dir / ".amm_installed.json").write_text('{"version": "x"}', encoding="utf-8")
    counts = catalog.counts()
    assert counts["installed"] == 1
    assert counts["available"] == counts["catalog"] - 1


def test_debug_share_url_is_token_gated(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(settings, "config_dir", tmp_path)
    monkeypatch.setattr(settings, "install_dir", tmp_path / "apps")
    monkeypatch.setattr(settings, "download_dir", tmp_path / "downloads")
    monkeypatch.setattr(settings, "media_dir", tmp_path / "media")
    monkeypatch.setattr(settings, "cache_dir", tmp_path / "cache")
    diagnostics.revoke_share()
    diagnostics.record_error("unit", "example failure for debug share")
    client = TestClient(create_app())

    missing = client.get("/debug/not-a-real-token")
    assert missing.status_code == 404

    created = client.post("/api/diagnostics/share")
    assert created.status_code == 200
    payload = created.json()
    url = payload["url"]
    token = payload["token"]
    assert token in url

    html = client.get(f"/debug/{token}")
    assert html.status_code == 200
    assert b"example failure for debug share" in html.content
    assert b"AIO Media Manager debug report" in html.content

    as_json = client.get(f"/debug/{token}", params={"format": "json"})
    assert as_json.status_code == 200
    body = as_json.json()
    assert body["catalog"]["counts"]["catalog"] >= 7
    assert any("example failure" in item["message"] for item in body["errors"])
    assert "recyclarr" in body
    assert body["recyclarr"].get("daemon") is False

    revoked = client.delete("/api/diagnostics/share")
    assert revoked.status_code == 200
    gone = client.get(f"/debug/{token}")
    assert gone.status_code == 404
