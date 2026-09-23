"""Cloudflare Tunnel token handling and API shape."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from api.app import create_app
from core.cloudflare_tunnel import CloudflareTunnelManager
from core.settings import Settings


def test_tunnel_status_without_token(tmp_path: Path):
    cfg = Settings(
        config_dir=tmp_path / "config",
        download_dir=tmp_path / "dl",
        media_dir=tmp_path / "media",
        cloudflare_tunnel_enabled=True,
    )
    mgr = CloudflareTunnelManager(cfg)
    status = mgr.status()
    assert status["enabled"] is True
    assert status["token_present"] is False
    assert "token" not in status
    assert status["connected"] is False
    assert mgr.command() is None


def test_persist_token_file_permissions(tmp_path: Path):
    cfg = Settings(
        config_dir=tmp_path / "config",
        download_dir=tmp_path / "dl",
        media_dir=tmp_path / "media",
        cloudflare_tunnel_enabled=True,
        cloudflare_tunnel_token="eyJtest-token-value",
    )
    mgr = CloudflareTunnelManager(cfg)
    path = mgr.persist_token()
    assert path is not None
    assert path.read_text(encoding="utf-8").strip() == "eyJtest-token-value"
    assert mgr.token_present() is True
    assert "eyJtest-token-value" not in str(mgr.status())


def test_system_info_includes_cloudflare_tunnel():
    client = TestClient(create_app())
    resp = client.get("/api/system/info")
    assert resp.status_code == 200
    data = resp.json()
    assert "cloudflare_tunnel" in data
    assert "token_present" in data["cloudflare_tunnel"]
    assert "token" not in data["cloudflare_tunnel"]


def test_cloudflare_tunnel_status_endpoint():
    client = TestClient(create_app())
    resp = client.get("/api/cloudflare/tunnel/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is False
    assert "token" not in body
