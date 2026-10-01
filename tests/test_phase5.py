"""Phase 5 VPN, transcoding, metrics, and reverse-proxy settings tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from api.app import create_app
from applications.qbittorrent import QBittorrentApp
from core.metrics import collect_metrics
from core.settings import Settings
from core.transcoding import probe_transcoding
from core.vpn import (
    TORRENT_NETNS,
    VPN_TUNNELED_APPS,
    VpnIsolationError,
    VpnManager,
    parse_vpn_dns_servers,
    parse_vpn_underlay_hosts,
    save_vpn_config_text,
    vpn_start_failure_detail,
)


def test_metrics_shape():
    data = collect_metrics()
    assert "cpu_percent" in data
    assert "memory" in data
    assert "disk" in data
    assert "network" in data
    assert isinstance(data["cpu_per_core"], list)
    assert isinstance(data["processes"], list)


def test_metrics_shape_when_process_cpu_is_blocked(monkeypatch):
    from core import metrics as metrics_mod

    metrics_mod._proc_cache.clear()
    supervisor = type("Supervisor", (), {})()
    supervisor.list_processes = lambda: [{"name": "sonarr", "state": "running", "pid": 4242}]
    monkeypatch.setattr(metrics_mod.ProcessSupervisor, "get", staticmethod(lambda: supervisor))

    class BlockedProc:
        pid = 4242

        def is_running(self):
            return True

        def cpu_percent(self, interval=None):
            raise SystemError("cpu_count_logical")

    monkeypatch.setattr(metrics_mod.psutil, "Process", lambda pid: BlockedProc())
    monkeypatch.setattr(
        metrics_mod.psutil,
        "cpu_count",
        lambda logical=True: (_ for _ in ()).throw(SystemError("cpu_count_logical")),
    )
    data = collect_metrics()
    assert "cpu_percent" in data
    assert isinstance(data["processes"], list)
    assert data["processes"][0]["name"] == "sonarr"
    assert data["processes"][0]["cpu_percent"] is None


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


def test_vpn_status_without_tunnel(tmp_path: Path, monkeypatch):
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
    assert status["kill_switch"] is True
    assert "privadovpn" in status["supported_providers"]
    monkeypatch.setattr(mgr, "_is_linux", lambda: False)
    cmd = mgr.wrap_torrent_command(["qbittorrent-nox"])
    assert cmd[0] == "qbittorrent-nox"


def test_vpn_wraps_without_netns_so_start_fails_closed(tmp_path: Path, monkeypatch):
    cfg = Settings(
        config_dir=tmp_path / "config",
        download_dir=tmp_path / "dl",
        media_dir=tmp_path / "media",
        vpn_enabled=True,
        vpn_enforce=False,
    )
    mgr = VpnManager(cfg)
    monkeypatch.setattr(mgr, "_is_linux", lambda: True)
    monkeypatch.setattr(mgr, "_netns_exists", lambda: False)
    monkeypatch.setattr("core.vpn.shutil.which", lambda name: "/sbin/ip" if name == "ip" else None)
    wrapped = mgr.wrap_torrent_command(["qbittorrent-nox"])
    assert wrapped[:4] == ["ip", "netns", "exec", TORRENT_NETNS]


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


def test_vpn_kill_switch_blocks_tunneled_apps_when_vpn_is_on(tmp_path: Path, monkeypatch):
    cfg = Settings(
        config_dir=tmp_path / "config",
        download_dir=tmp_path / "dl",
        media_dir=tmp_path / "media",
        vpn_enabled=True,
        vpn_enforce=False,
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
    assert mgr.status()["kill_switch"] is True


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


def test_parse_vpn_dns_from_wireguard_and_openvpn():
    assert parse_vpn_dns_servers("DNS = 10.2.0.1, 10.2.0.2\n") == ["10.2.0.1", "10.2.0.2"]
    assert parse_vpn_dns_servers("dhcp-option DNS 103.86.96.100\n") == ["103.86.96.100"]
    assert parse_vpn_dns_servers("[Interface]\nPrivateKey = x\n") == []
    assert parse_vpn_underlay_hosts("Endpoint = 203.0.113.10:51820\n") == ["203.0.113.10"]
    assert parse_vpn_underlay_hosts("remote 198.51.100.8 1194\n") == ["198.51.100.8"]


def test_vpn_start_failure_explains_missing_wireguard_go():
    text = vpn_start_failure_detail(127, "", "")
    assert "wireguard-go" in text
    assert "OpenVPN" in text


def test_vpn_start_failure_explains_missing_resolvconf():
    text = vpn_start_failure_detail(
        127,
        "[#] resolvconf -a wg0 -m 0 -x\n/usr/bin/wg-quick: line 32: resolvconf: command not found\n",
        "",
    )
    assert "resolvconf" in text.lower()
    assert "DNS" in text


def test_host_veth_guard_allows_established_webui_replies(tmp_path: Path, monkeypatch):
    cfg = Settings(
        config_dir=tmp_path / "config",
        download_dir=tmp_path / "dl",
        media_dir=tmp_path / "media",
        vpn_enabled=True,
    )
    mgr = VpnManager(cfg)
    calls: list[list[str]] = []
    monkeypatch.setattr(mgr, "_underlay_ips", lambda: [])

    def fake_iptables(args: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(list(args))
        return subprocess.CompletedProcess(args, 1, "", "")

    monkeypatch.setattr(mgr, "_host_iptables", fake_iptables)
    mgr._apply_host_veth_guard()
    blob = " ".join(" ".join(item) for item in calls)
    assert "ESTABLISHED,RELATED" in blob
    assert any(item[:3] == ["-I", "FORWARD", "1"] for item in calls)


def test_forward_local_ports_dnat_published_and_loopback(tmp_path: Path, monkeypatch):
    cfg = Settings(
        config_dir=tmp_path / "config",
        download_dir=tmp_path / "dl",
        media_dir=tmp_path / "media",
        vpn_enabled=True,
    )
    mgr = VpnManager(cfg)
    calls: list[list[str]] = []
    monkeypatch.setattr(mgr, "_webui_ports", lambda: {"qbittorrent": 8081, "prowlarr": 9696})
    monkeypatch.setattr(
        "core.vpn.shutil.which",
        lambda name: "/sbin/iptables" if name == "iptables" else None,
    )
    monkeypatch.setattr("core.vpn.subprocess.run", lambda *a, **k: subprocess.CompletedProcess(a, 0, "", ""))

    def fake_iptables(args: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(list(args))
        return subprocess.CompletedProcess(args, 1, "", "")

    monkeypatch.setattr(mgr, "_host_iptables", fake_iptables)
    mgr._forward_local_ports()
    blob = " ".join(" ".join(item) for item in calls)
    assert "PREROUTING" in blob
    assert "127.0.0.1" in blob
    assert "8081" in blob
    assert "9696" in blob
    assert "MASQUERADE" in blob


def test_stale_netns_file_is_not_ready(tmp_path: Path, monkeypatch):
    cfg = Settings(
        config_dir=tmp_path / "config",
        download_dir=tmp_path / "dl",
        media_dir=tmp_path / "media",
        vpn_enabled=True,
    )
    mgr = VpnManager(cfg)
    bind = tmp_path / "amm-torrent"
    bind.write_text("", encoding="utf-8")
    monkeypatch.setattr(mgr, "_netns_bind_path", lambda: bind)
    monkeypatch.setattr(
        mgr,
        "_ip",
        lambda args: subprocess.CompletedProcess(args, 1, "", "Peer netns reference is invalid."),
    )
    assert mgr._netns_exists() is False


def test_persisted_vpn_enabled_beats_compose_env(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AMM_VPN_ENABLED", "false")
    monkeypatch.setenv("AMM_VPN_ENFORCE", "false")
    cfg = Settings(
        config_dir=tmp_path / "config",
        download_dir=tmp_path / "dl",
        media_dir=tmp_path / "media",
        vpn_enabled=False,
        vpn_enforce=False,
    )
    cfg.initialise()
    cfg.vpn_enabled = True
    cfg.vpn_enforce = True
    cfg.save()
    reloaded = Settings(
        config_dir=cfg.config_dir,
        download_dir=cfg.download_dir,
        media_dir=cfg.media_dir,
        vpn_enabled=False,
        vpn_enforce=False,
    )
    reloaded.initialise()
    assert reloaded.vpn_enabled is True
    assert reloaded.vpn_enforce is True


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
    client = TestClient(create_app(), base_url="http://127.0.0.1", client=("127.0.0.1", 50000))
    resp = client.get("/api/system/info")
    assert resp.status_code == 200
    data = resp.json()
    assert data["debug"] is True
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
