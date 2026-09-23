"""Phase 5 VPN, transcoding, metrics, and reverse-proxy settings tests."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from api.app import create_app
from applications.qbittorrent import QBittorrentApp
from core.metrics import collect_metrics
from core.settings import Settings
from core.transcoding import probe_transcoding
from core.vpn import VpnManager


def test_metrics_shape():
    data = collect_metrics()
    assert "cpu_percent" in data
    assert "memory" in data
    assert "disk" in data
    assert "network" in data
    assert isinstance(data["cpu_per_core"], list)


def test_transcoding_probe_does_not_require_gpu():
    probe = probe_transcoding()
    assert "available" in probe
    assert "vaapi" in probe
    assert "nvidia" in probe
    assert "notes" in probe


def test_vpn_status_without_tunnel(tmp_path: Path):
    cfg = Settings(
        config_dir=tmp_path / "config",
        download_dir=tmp_path / "dl",
        media_dir=tmp_path / "media",
        vpn_enabled=True,
        vpn_enforce=True,
        vpn_provider="privadovpn",
    )
    mgr = VpnManager(cfg)
    status = mgr.status()
    assert status["enabled"] is True
    assert status["usenet_bypasses_vpn"] is True
    assert status["tunnel_up"] is False
    assert "privadovpn" in status["supported_providers"]
    cmd = mgr.wrap_torrent_command(["qbittorrent-nox"])
    assert cmd[0] == "qbittorrent-nox"


def test_qbittorrent_start_command_not_netns_on_non_linux(tmp_path: Path):
    app = QBittorrentApp(base_config_dir=tmp_path, base_install_dir=tmp_path)
    exe = tmp_path / "qbittorrent-nox"
    exe.write_text("x", encoding="utf-8")
    exe.chmod(0o755)
    cmd = app.build_start_command(exe)
    assert "qbittorrent-nox" in cmd[-4] or str(exe) == cmd[0]


def test_system_info_includes_phase5_fields():
    client = TestClient(create_app())
    resp = client.get("/api/system/info")
    assert resp.status_code == 200
    data = resp.json()
    assert "metrics" in data
    assert "transcoding" in data
    assert "vpn" in data
    assert "cloudflare_tunnel" in data


def test_vpn_status_endpoint():
    client = TestClient(create_app())
    resp = client.get("/api/vpn/status")
    assert resp.status_code == 200
    assert resp.json()["usenet_bypasses_vpn"] is True


def test_trusted_proxy_setting(tmp_path: Path):
    cfg = Settings(
        config_dir=tmp_path / "c",
        download_dir=tmp_path / "d",
        media_dir=tmp_path / "m",
        trusted_proxies="10.0.0.1,10.0.0.2",
        root_path="/amm",
    )
    assert "10.0.0.1" in cfg.trusted_proxies
    assert cfg.root_path == "/amm"
    serial = cfg.as_serialisable_dict()
    assert serial["vpn_enabled"] is False
