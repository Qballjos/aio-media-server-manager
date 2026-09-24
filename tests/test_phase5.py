"""Phase 5 VPN, transcoding, metrics, and reverse-proxy settings tests."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from api.app import create_app
from applications.qbittorrent import QBittorrentApp
from core.metrics import collect_metrics
from core.settings import Settings
from core.transcoding import probe_transcoding
from core.vpn import TORRENT_NETNS, VPN_TUNNELED_APPS, VpnIsolationError, VpnManager, save_vpn_config_text


def test_metrics_shape():
    data = collect_metrics()
    assert "cpu_percent" in data
    assert "memory" in data
    assert "disk" in data
    assert "network" in data
    assert isinstance(data["cpu_per_core"], list)
    assert isinstance(data["processes"], list)


def test_process_metrics_include_cpu_and_memory(monkeypatch):
    from core import metrics as metrics_mod

    metrics_mod._proc_cache.clear()
    supervisor = type("Supervisor", (), {})()
    supervisor.list_processes = lambda: [{"name": "sonarr", "state": "running", "pid": 4242}]
    monkeypatch.setattr(metrics_mod.ProcessSupervisor, "get", staticmethod(lambda: supervisor))

    class FakeMem:
        rss = 50 * 1024 * 1024

    class FakeProc:
        pid = 4242

        def is_running(self):
            return True

        def cpu_percent(self, interval=None):
            return 12.5

        def memory_info(self):
            return FakeMem()

        def memory_percent(self):
            return 3.2

        def children(self, recursive=False):
            return []

    monkeypatch.setattr(metrics_mod.psutil, "Process", lambda pid: FakeProc())
    rows = metrics_mod._process_metrics()
    assert rows[0]["name"] == "sonarr"
    assert rows[0]["cpu_percent"] == 12.5
    assert rows[0]["memory_rss"] == 50 * 1024 * 1024
    assert rows[0]["memory_percent"] == 3.2


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
    assert status["tunneled_apps"] == ["flaresolverr", "prowlarr", "qbittorrent"]
    assert status["unprotected_apps"] == []
    assert status["tunnel_up"] is False
    assert "privadovpn" in status["supported_providers"]
    cmd = mgr.wrap_torrent_command(["qbittorrent-nox"])
    assert cmd[0] == "qbittorrent-nox"


def test_vpn_wraps_when_linux_netns_exists(tmp_path: Path, monkeypatch):
    cfg = Settings(
        config_dir=tmp_path / "config",
        download_dir=tmp_path / "dl",
        media_dir=tmp_path / "media",
        vpn_enabled=True,
        vpn_enforce=True,
    )
    mgr = VpnManager(cfg)
    monkeypatch.setattr(mgr, "_is_linux", lambda: True)
    monkeypatch.setattr(mgr, "_netns_exists", lambda: True)
    monkeypatch.setattr("core.vpn.shutil.which", lambda name: "/sbin/ip" if name == "ip" else None)
    wrapped = mgr.wrap_isolated_command(["Prowlarr", "-nobrowser"])
    assert wrapped[:4] == ["ip", "netns", "exec", TORRENT_NETNS]
    assert wrapped[-1] == "-nobrowser"


def test_vpn_kill_switch_blocks_tunneled_apps(tmp_path: Path, monkeypatch):
    cfg = Settings(
        config_dir=tmp_path / "config",
        download_dir=tmp_path / "dl",
        media_dir=tmp_path / "media",
        vpn_enabled=True,
        vpn_enforce=True,
    )
    mgr = VpnManager(cfg)
    monkeypatch.setattr(mgr, "_is_linux", lambda: True)
    monkeypatch.setattr(mgr, "_netns_exists", lambda: False)
    monkeypatch.setattr(mgr, "_tunnel_up", lambda: False)
    for name in VPN_TUNNELED_APPS:
        try:
            mgr.assert_can_start_tunneled_app(name)
            raise AssertionError(f"expected kill switch for {name}")
        except VpnIsolationError:
            pass
    mgr.assert_can_start_tunneled_app("sabnzbd")
    assert "flaresolverr" in VPN_TUNNELED_APPS


def test_save_vpn_config_text_writes_default_path(tmp_path: Path):
    cfg = Settings(
        config_dir=tmp_path / "config",
        download_dir=tmp_path / "dl",
        media_dir=tmp_path / "media",
    )
    dest = save_vpn_config_text(
        cfg,
        "client\ndev tun\nremote vpn.example 1194\n",
        protocol="openvpn",
    )
    assert dest == cfg.config_dir / "vpn" / "client.ovpn"
    assert dest.is_file()
    assert "remote vpn.example" in dest.read_text(encoding="utf-8")


def test_flaresolverr_start_command_wraps_on_linux(tmp_path: Path, monkeypatch):
    from applications.community import FlaresolverrApp
    from core import vpn as vpn_mod

    cfg = Settings(
        config_dir=tmp_path / "config",
        download_dir=tmp_path / "dl",
        media_dir=tmp_path / "media",
        vpn_enabled=True,
    )
    mgr = VpnManager(cfg)
    monkeypatch.setattr(mgr, "_is_linux", lambda: True)
    monkeypatch.setattr(mgr, "_netns_exists", lambda: True)
    monkeypatch.setattr("core.vpn.shutil.which", lambda name: "/sbin/ip" if name == "ip" else None)
    monkeypatch.setattr(vpn_mod, "vpn_manager", mgr)
    app = FlaresolverrApp(base_config_dir=tmp_path, base_install_dir=tmp_path)
    exe = tmp_path / "flaresolverr"
    exe.write_text("x", encoding="utf-8")
    exe.chmod(0o755)
    cmd = app.build_start_command(exe)
    assert cmd[:4] == ["ip", "netns", "exec", TORRENT_NETNS]


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
    assert "library" in data
    assert "tv" in data["library"]["libraries"]
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
