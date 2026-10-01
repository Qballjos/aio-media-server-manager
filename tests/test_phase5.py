"""Phase 5 VPN, transcoding, metrics, and reverse-proxy settings tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from applications.qbittorrent import QBittorrentApp
from core.metrics import collect_metrics
from core.settings import Settings
from core.transcoding import probe_transcoding
from core.vpn import (
    TORRENT_NETNS,
    VPN_APP_GID,
    VPN_APP_UID,
    VPN_TUNNELED_APPS,
    VpnIsolationError,
    VpnManager,
    ensure_wireguard_persistent_keepalive,
    ensure_wireguard_table_off,
    parse_vpn_dns_servers,
    parse_vpn_underlay_hosts,
    rewrite_wireguard_endpoints,
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
    assert status["last_error"] == ""
    assert "privadovpn" in status["supported_providers"]
    monkeypatch.setattr(mgr, "_is_linux", lambda: False)
    cmd = mgr.wrap_torrent_command(["qbittorrent-nox"])
    assert cmd[0] == "qbittorrent-nox"


def test_vpn_wraps_wireguard_with_setpriv_uid(tmp_path: Path, monkeypatch):
    cfg = Settings(
        config_dir=tmp_path / "config",
        download_dir=tmp_path / "dl",
        media_dir=tmp_path / "media",
        vpn_enabled=True,
        vpn_protocol="wireguard",
    )
    mgr = VpnManager(cfg)
    monkeypatch.setattr(mgr, "_is_linux", lambda: True)
    monkeypatch.setattr(mgr, "_ensure_vpn_app_user", lambda: None)
    monkeypatch.setattr(
        "core.vpn.shutil.which",
        lambda name: "/usr/bin/setpriv" if name == "setpriv" else None,
    )
    wrapped = mgr.wrap_torrent_command(["qbittorrent-nox"])
    assert wrapped[:4] == ["setpriv", f"--reuid={VPN_APP_UID}", f"--regid={VPN_APP_GID}", "--clear-groups"]
    assert "qbittorrent-nox" in wrapped


def test_vpn_wraps_openvpn_with_netns(tmp_path: Path, monkeypatch):
    cfg = Settings(
        config_dir=tmp_path / "config",
        download_dir=tmp_path / "dl",
        media_dir=tmp_path / "media",
        vpn_enabled=True,
        vpn_protocol="openvpn",
    )
    mgr = VpnManager(cfg)
    monkeypatch.setattr(mgr, "_is_linux", lambda: True)
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
    assert mgr.tunneled_apps_allowed() is False


def test_tunneled_apps_allowed_when_vpn_off_or_tunnel_up(tmp_path: Path, monkeypatch):
    off = VpnManager(
        Settings(
            config_dir=tmp_path / "config",
            download_dir=tmp_path / "dl",
            media_dir=tmp_path / "media",
            vpn_enabled=False,
        )
    )
    assert off.tunneled_apps_allowed() is True
    for name in VPN_TUNNELED_APPS:
        off.assert_can_start_tunneled_app(name)
    assert off.wrap_isolated_command(["qbittorrent-nox"]) == ["qbittorrent-nox"]
    mgr = VpnManager(
        Settings(
            config_dir=tmp_path / "config",
            download_dir=tmp_path / "dl",
            media_dir=tmp_path / "media",
            vpn_enabled=True,
        )
    )
    monkeypatch.setattr(mgr, "_is_linux", lambda: True)
    monkeypatch.setattr(mgr, "_netns_exists", lambda: True)
    monkeypatch.setattr(mgr, "_tunnel_up", lambda: True)
    assert mgr.tunneled_apps_allowed() is True


def test_kill_switch_lifts_when_vpn_switch_turns_off(tmp_path: Path, monkeypatch):
    cfg = Settings(
        config_dir=tmp_path / "config",
        download_dir=tmp_path / "dl",
        media_dir=tmp_path / "media",
        vpn_enabled=True,
    )
    mgr = VpnManager(cfg)
    monkeypatch.setattr(mgr, "_is_linux", lambda: True)
    monkeypatch.setattr(mgr, "_netns_exists", lambda: False)
    monkeypatch.setattr(mgr, "_tunnel_up", lambda: False)
    for name in VPN_TUNNELED_APPS:
        try:
            mgr.assert_can_start_tunneled_app(name)
            raise AssertionError(f"expected block for {name}")
        except VpnIsolationError:
            pass
    cfg.vpn_enabled = False
    assert mgr.tunneled_apps_allowed() is True
    assert mgr.status()["kill_switch"] is False
    for name in VPN_TUNNELED_APPS:
        mgr.assert_can_start_tunneled_app(name)
    assert mgr.wrap_isolated_command(["prowlarr"]) == ["prowlarr"]


@pytest.mark.asyncio
async def test_enforce_vpn_isolation_stops_qbittorrent(monkeypatch):
    from unittest.mock import MagicMock

    from core.integrations import lifecycle as lifecycle_mod

    stopped: list[str] = []
    supervisor = MagicMock()
    supervisor.status.side_effect = lambda name: MagicMock(
        value="running" if name == "qbittorrent" else "stopped"
    )

    async def fake_stop(name: str) -> None:
        stopped.append(name)

    supervisor.stop = fake_stop
    catalog = MagicMock()
    catalog.has.return_value = False
    monkeypatch.setattr(lifecycle_mod.vpn_manager, "tunneled_apps_allowed", lambda: False)
    monkeypatch.setattr(lifecycle_mod.ProcessSupervisor, "get", staticmethod(lambda: supervisor))
    monkeypatch.setattr("applications.catalog.ApplicationCatalog", lambda: catalog)

    result = await lifecycle_mod.enforce_vpn_isolation()
    assert result == ["qbittorrent"]
    assert stopped == ["qbittorrent"]


@pytest.mark.asyncio
async def test_enforce_vpn_isolation_noop_when_allowed(monkeypatch):
    from core.integrations.lifecycle import enforce_vpn_isolation

    monkeypatch.setattr(
        "core.integrations.lifecycle.vpn_manager.tunneled_apps_allowed",
        lambda: True,
    )
    assert await enforce_vpn_isolation() == []


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
    assert parse_vpn_underlay_hosts("Endpoint = vpn.example.com:51820\n") == ["vpn.example.com"]


def test_rewrite_wireguard_endpoints_pins_hostname():
    text = "[Peer]\nPublicKey = abc\nEndpoint = vpn.example.com:51820\nAllowedIPs = 0.0.0.0/0\n"
    out = rewrite_wireguard_endpoints(text, {"vpn.example.com": "203.0.113.9"})
    assert "Endpoint = 203.0.113.9:51820" in out
    assert "vpn.example.com" not in out


def test_ensure_wireguard_table_off_inserts_and_replaces():
    added = ensure_wireguard_table_off("[Interface]\nPrivateKey = x\nAddress = 10.0.0.2/32\n\n[Peer]\n")
    assert "Table = off" in added
    assert added.index("Table = off") < added.index("[Peer]")
    replaced = ensure_wireguard_table_off("[Interface]\nTable = auto\nPrivateKey = x\n")
    assert "Table = auto" not in replaced
    assert "Table = off" in replaced
    assert replaced.count("Table =") == 1


def test_ensure_wireguard_persistent_keepalive_inserts_and_normalizes():
    added = ensure_wireguard_persistent_keepalive(
        "[Interface]\nPrivateKey = x\n\n[Peer]\nPublicKey = y\nEndpoint = 1.2.3.4:51820\n"
    )
    assert "PersistentKeepalive = 25" in added
    assert added.index("[Peer]") < added.index("PersistentKeepalive = 25")
    replaced = ensure_wireguard_persistent_keepalive(
        "[Peer]\nPublicKey = y\nPersistentKeepalive = 10\n",
        interval=25,
    )
    assert "PersistentKeepalive = 10" not in replaced
    assert "PersistentKeepalive = 25" in replaced
    assert replaced.count("PersistentKeepalive") == 1


def test_bootstrap_ips_are_underlay_endpoints_only(tmp_path: Path, monkeypatch):
    cfg = Settings(
        config_dir=tmp_path / "config",
        download_dir=tmp_path / "dl",
        media_dir=tmp_path / "media",
        vpn_enabled=True,
    )
    mgr = VpnManager(cfg)
    monkeypatch.setattr(mgr, "_underlay_ips", lambda: ["203.0.113.10"])
    ips = mgr._bootstrap_ips()
    assert ips == ["203.0.113.10"]
    assert "1.1.1.1" not in ips
    assert "9.9.9.9" not in ips


def test_dns_for_netns_prefers_profile_then_public_fallback(tmp_path: Path, monkeypatch):
    cfg = Settings(
        config_dir=tmp_path / "config",
        download_dir=tmp_path / "dl",
        media_dir=tmp_path / "media",
        vpn_enabled=True,
    )
    mgr = VpnManager(cfg)
    monkeypatch.setattr(mgr, "_profile_dns_servers", lambda: ["10.64.0.1", "127.0.0.11"])
    servers = mgr._dns_for_netns()
    assert servers[0] == "10.64.0.1"
    assert "127.0.0.11" not in servers
    assert "1.1.1.1" in servers
    assert "9.9.9.9" in servers


def test_wireguard_covers_default_route_and_sanitize():
    from core.vpn import (
        parse_wireguard_endpoint,
        parse_wireguard_tunnel_address,
        rewrite_wireguard_endpoint_host_port,
        sanitize_wireguard_runtime,
        wireguard_covers_default_route,
    )

    full = (
        "[Interface]\nPrivateKey = x\nAddress = 10.64.1.2/32\nDNS = 1.1.1.1\n"
        "PostUp = iptables -A FORWARD -j ACCEPT\n\n"
        "[Peer]\nEndpoint = vpn.example:51820\nAllowedIPs = 0.0.0.0/0, ::/0\n"
    )
    assert wireguard_covers_default_route(full)
    assert parse_wireguard_tunnel_address(full) == "10.64.1.2"
    assert parse_wireguard_endpoint(full) == ("vpn.example", 51820)
    relayed = rewrite_wireguard_endpoint_host_port(full, "10.200.200.1", 51820)
    assert "Endpoint = 10.200.200.1:51820" in relayed
    cleaned = sanitize_wireguard_runtime(full)
    assert "DNS" not in cleaned
    assert "PostUp" not in cleaned
    assert "AllowedIPs" in cleaned
    assert not wireguard_covers_default_route("[Peer]\nAllowedIPs = 10.0.0.0/8\n")


def test_vpn_endpoint_relay_forwards_datagrams():
    import socket
    import threading
    import time
    from core.vpn_relay import WgEndpointRelay

    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind(("127.0.0.1", 0))
    server_port = server.getsockname()[1]
    got: dict[str, bytes] = {}

    def serve() -> None:
        data, addr = server.recvfrom(256)
        got["data"] = data
        got["addr"] = addr[0].encode()
        server.sendto(b"pong", addr)

    threading.Thread(target=serve, daemon=True).start()

    listen = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    listen.bind(("127.0.0.1", 0))
    listen_port = listen.getsockname()[1]
    listen.close()

    relay = WgEndpointRelay()
    assert relay.ensure(
        listen_host="127.0.0.1",
        listen_port=listen_port,
        dest_host="127.0.0.1",
        dest_port=server_port,
    )
    client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client.settimeout(3)
    client.sendto(b"ping", ("127.0.0.1", listen_port))
    reply, _ = client.recvfrom(256)
    assert reply == b"pong"
    time.sleep(0.05)
    assert got.get("data") == b"ping"
    client.close()
    relay.stop()
    server.close()


def test_write_netns_resolv_is_idempotent(tmp_path: Path, monkeypatch):
    import os

    resolv = tmp_path / "resolv.conf"
    writes = {"n": 0}
    real_replace = os.replace

    def counting_replace(src, dst):
        writes["n"] += 1
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", counting_replace)

    def write_resolv(servers: list[str]) -> None:
        content = "".join(f"nameserver {item}\n" for item in servers)
        if resolv.is_file() and resolv.read_text(encoding="utf-8") == content:
            return
        tmp = resolv.with_name(resolv.name + ".tmp")
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, resolv)

    write_resolv(["1.1.1.1"])
    write_resolv(["1.1.1.1"])
    assert writes["n"] == 1
    assert resolv.read_text(encoding="utf-8") == "nameserver 1.1.1.1\n"


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


def test_vpn_start_failure_explains_nft_iptables_restore():
    text = vpn_start_failure_detail(
        1,
        "[#] iptables-restore -n\niptables-restore v1.8.9 (nf_tables): "
        "Could not fetch rule set generation id: Invalid argument\n",
        "",
    )
    assert "Table = off" in text
    assert "iptables-restore" in text.lower()


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


def test_forward_local_ports_starts_webui_proxy(tmp_path: Path, monkeypatch):
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
        "core.vpn.vpn_webui_proxy.ensure",
        lambda ports, dest_host="10.200.200.2": [8081, 9696],
    )
    monkeypatch.setattr("core.vpn.subprocess.run", lambda *a, **k: subprocess.CompletedProcess(a, 0, "", ""))

    def fake_iptables(args: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(list(args))
        return subprocess.CompletedProcess(args, 1, "", "")

    monkeypatch.setattr(mgr, "_host_iptables", fake_iptables)
    mgr._forward_local_ports()
    blob = " ".join(" ".join(item) for item in calls)
    assert "FORWARD" in blob
    assert "10.200.200.2" in blob


def test_forward_local_ports_dnat_fallback_when_proxy_fails(tmp_path: Path, monkeypatch):
    cfg = Settings(
        config_dir=tmp_path / "config",
        download_dir=tmp_path / "dl",
        media_dir=tmp_path / "media",
        vpn_enabled=True,
    )
    mgr = VpnManager(cfg)
    calls: list[list[str]] = []
    monkeypatch.setattr(mgr, "_webui_ports", lambda: {"qbittorrent": 8081, "prowlarr": 9696})
    monkeypatch.setattr("core.vpn.vpn_webui_proxy.ensure", lambda ports, dest_host="10.200.200.2": [])
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


def test_vpn_webui_proxy_forwards_bytes():
    import socket
    import threading
    import time
    from core.vpn_proxy import VpnWebUiProxy

    backend = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    backend.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    backend.bind(("127.0.0.1", 0))
    backend.listen(1)
    backend_port = backend.getsockname()[1]
    received: dict[str, bytes] = {}

    def accept_backend() -> None:
        conn, _ = backend.accept()
        received["data"] = conn.recv(64)
        conn.sendall(b"pong")
        conn.close()

    threading.Thread(target=accept_backend, daemon=True).start()

    proxy = VpnWebUiProxy()
    listen_port = None
    for _ in range(20):
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind(("0.0.0.0", 0))
        candidate = probe.getsockname()[1]
        probe.close()
        time.sleep(0.02)
        if proxy.ensure({candidate: backend_port}, dest_host="127.0.0.1") == [candidate]:
            listen_port = candidate
            break
    assert listen_port is not None
    assert listen_port in proxy.listening_ports()

    client = socket.create_connection(("127.0.0.1", listen_port), timeout=3)
    client.sendall(b"ping")
    assert client.recv(64) == b"pong"
    client.close()
    proxy.stop_all()
    assert proxy.listening_ports() == []
    assert received.get("data") == b"ping"
    backend.close()


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
        vpn_protocol="wireguard",
    )
    mgr = VpnManager(cfg)
    monkeypatch.setattr(mgr, "_is_linux", lambda: True)
    monkeypatch.setattr(mgr, "_ensure_vpn_app_user", lambda: None)
    monkeypatch.setattr(
        "core.vpn.shutil.which",
        lambda name: "/usr/bin/setpriv" if name == "setpriv" else None,
    )
    monkeypatch.setattr(vpn_mod, "vpn_manager", mgr)
    app = FlaresolverrApp(base_config_dir=tmp_path, base_install_dir=tmp_path)
    exe = tmp_path / "flaresolverr"
    exe.write_text("x", encoding="utf-8")
    exe.chmod(0o755)
    cmd = app.build_start_command(exe)
    assert cmd[:4] == ["setpriv", f"--reuid={VPN_APP_UID}", f"--regid={VPN_APP_GID}", "--clear-groups"]


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
