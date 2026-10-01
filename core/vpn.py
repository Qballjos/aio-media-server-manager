"""
core/vpn.py — Optional VPN isolation for BitTorrent, Prowlarr, and Flaresolverr.

Usenet (SABnzbd/NZBGet) always stays on the host network. When VPN is enabled
on Linux, qBittorrent, Prowlarr, and Flaresolverr run inside the `amm-torrent`
netns so their egress uses the tunnel only. Local WebUIs are published via a
TCP proxy in the main netns (Docker/Synology cannot DNAT reliably into the
torrent namespace).
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from core.settings import Settings, settings
from core.supervisor import ProcessSupervisor
from core.vpn_proxy import vpn_webui_proxy

logger = logging.getLogger(__name__)

PROVIDERS = ("privadovpn", "mullvad", "protonvpn", "airvpn", "ivpn", "custom")
TORRENT_NETNS = "amm-torrent"
VPN_TUNNELED_APPS = frozenset({"qbittorrent", "prowlarr", "flaresolverr"})
MAX_VPN_CONFIG_BYTES = 256 * 1024
_VETH_HOST = "amm-veth-h"
_VETH_NS = "amm-veth-n"
_NS_HOST_IP = "10.200.200.1"
_NS_PEER_IP = "10.200.200.2"
_DEFAULT_PORTS = {"qbittorrent": 8081, "prowlarr": 9696, "flaresolverr": 8191}
_FALLBACK_DNS = ("1.1.1.1", "9.9.9.9")
_KS_CHAIN = "AMM-KS"


class VpnIsolationError(RuntimeError):
    """Raised when a tunneled app would leak traffic off the VPN."""


def default_vpn_config_filename(protocol: str) -> str:
    return "client.ovpn" if str(protocol).lower() == "openvpn" else "wg0.conf"


def vpn_config_destination(app_settings: Settings, *, protocol: str | None = None, path: str | None = None) -> Path:
    requested = (path or "").strip()
    if requested:
        return Path(requested).expanduser()
    proto = (protocol or app_settings.vpn_protocol or "wireguard").strip().lower()
    return Path(app_settings.config_dir) / "vpn" / default_vpn_config_filename(proto)


def save_vpn_config_text(
    app_settings: Settings,
    text: str,
    *,
    protocol: str | None = None,
    path: str | None = None,
) -> Path:
    """Write an uploaded or pasted WireGuard/OpenVPN profile and point settings at it."""
    raw = (text or "").replace("\x00", "").strip()
    if not raw:
        raise ValueError("VPN config is empty.")
    encoded = raw.encode("utf-8")
    if len(encoded) > MAX_VPN_CONFIG_BYTES:
        raise ValueError("VPN config is too large (256 KB maximum).")
    proto = (protocol or app_settings.vpn_protocol or "wireguard").strip().lower()
    if proto not in {"wireguard", "openvpn"}:
        raise ValueError("vpn_protocol must be wireguard or openvpn.")
    lowered = raw.lower()
    if proto == "wireguard" and "[interface]" not in lowered:
        raise ValueError("That does not look like a WireGuard config ([Interface] is missing).")
    if proto == "openvpn" and not any(token in lowered for token in ("remote ", "dev tun", "dev tap", "client")):
        raise ValueError("That does not look like an OpenVPN profile.")
    dest = vpn_config_destination(app_settings, protocol=proto, path=path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(raw if raw.endswith("\n") else raw + "\n", encoding="utf-8")
    try:
        dest.chmod(0o600)
    except OSError:
        pass
    app_settings.vpn_config_path = dest
    return dest


def parse_vpn_dns_servers(text: str) -> list[str]:
    """Read DNS servers from a WireGuard or OpenVPN profile."""
    servers: list[str] = []
    seen: set[str] = set()
    for raw in (text or "").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        lower = line.lower()
        values = ""
        if lower.startswith("dns"):
            _, _, values = line.partition("=")
            if not values:
                _, _, values = line.partition(" ")
        elif "dhcp-option" in lower and "dns" in lower:
            values = line.split("DNS", 1)[-1] if "DNS" in line else line.split("dns", 1)[-1]
        else:
            continue
        for token in values.replace(";", ",").split(","):
            host = token.strip().split("%", 1)[0]
            if host.count(":") == 1 and host.rsplit(":", 1)[-1].isdigit():
                host = host.rsplit(":", 1)[0]
            if _is_dns_address(host) and host not in seen:
                seen.add(host)
                servers.append(host)
    return servers


def _is_dns_address(value: str) -> bool:
    host = (value or "").strip()
    if not host or host.startswith("-"):
        return False
    if host.count(".") == 3:
        parts = host.split(".")
        try:
            return all(0 <= int(part) <= 255 for part in parts)
        except ValueError:
            return False
    return ":" in host


def parse_vpn_underlay_hosts(text: str) -> list[str]:
    """VPN server hostnames/IPs that must use the house underlay for the handshake."""
    hosts: list[str] = []
    seen: set[str] = set()
    for raw in (text or "").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        lower = line.lower()
        host = ""
        if lower.startswith("endpoint"):
            _, _, rest = line.partition("=")
            if not rest.strip():
                _, _, rest = line.partition(" ")
            host, _port = _split_endpoint(rest.strip())
        elif lower.startswith("remote ") or lower.startswith("remote\t"):
            parts = line.split()
            if len(parts) >= 2:
                host = parts[1].strip()
        if host and host not in seen:
            seen.add(host)
            hosts.append(host)
    return hosts


def _split_endpoint(value: str) -> tuple[str, str]:
    raw = (value or "").strip()
    if raw.startswith("["):
        host, _, rest = raw[1:].partition("]")
        port = rest.lstrip(":").split()[0].strip() if rest else ""
        return host.strip(), port or "51820"
    if raw.count(":") == 1:
        host, _, port = raw.partition(":")
        return host.strip(), (port.split()[0].strip() or "51820")
    return raw, "51820"


def rewrite_wireguard_endpoints(text: str, resolved: dict[str, str]) -> str:
    """Pin Endpoint hostnames to IPs so wg-quick inside amm-torrent does not need DNS."""
    if not resolved:
        return text
    lines: list[str] = []
    for raw in text.splitlines(keepends=True):
        stripped = raw.split("#", 1)[0].strip()
        if not stripped.lower().startswith("endpoint"):
            lines.append(raw)
            continue
        prefix, sep, rest = raw.partition("=")
        if not sep:
            prefix, sep, rest = raw.partition(" ")
        value = rest.strip()
        if not value:
            lines.append(raw)
            continue
        host, port = _split_endpoint(value.split("#", 1)[0].strip())
        ip = resolved.get(host) or resolved.get(host.lower())
        if not ip or ip == host:
            lines.append(raw)
            continue
        newline = "\n" if raw.endswith("\n") else ""
        lines.append(f"{prefix}{sep} {ip}:{port}{newline}")
    return "".join(lines)


def ensure_wireguard_table_off(text: str) -> str:
    """Stop wg-quick from running iptables-restore (nft addrtype fails in Docker/NAS netns)."""
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    in_interface = False
    saw_table = False

    def _flush_table() -> None:
        nonlocal saw_table
        if in_interface and not saw_table:
            if out and not str(out[-1]).endswith("\n"):
                out[-1] = str(out[-1]) + "\n"
            out.append("Table = off\n")
            saw_table = True

    for raw in lines:
        stripped = raw.split("#", 1)[0].strip()
        lower = stripped.lower()
        if lower.startswith("[") and lower.endswith("]"):
            _flush_table()
            in_interface = lower == "[interface]"
            saw_table = False
            out.append(raw)
            continue
        if in_interface and lower.startswith("table"):
            newline = "\n" if raw.endswith("\n") else ""
            prefix, sep, _rest = raw.partition("=")
            if not sep:
                prefix, sep, _rest = raw.partition(" ")
            out.append(f"{prefix}{sep} off{newline}")
            saw_table = True
            continue
        out.append(raw)
    _flush_table()
    return "".join(out)


def vpn_start_failure_detail(returncode: int, stderr: str, stdout: str) -> str:
    detail = (stderr or stdout or "").strip()
    lower = detail.lower()
    if "resolvconf" in lower and "command not found" in lower:
        hint = (
            "wg-quick needs resolvconf for DNS= in the WireGuard profile. "
            "The appliance should install a shim automatically; if this persists, "
            "remove the DNS line or install openresolv."
        )
        return f"{hint} {detail}".strip()[:2000]
    if (
        "iptables-restore" in lower
        or "addrtype" in lower
        or "rule set generation id" in lower
    ):
        hint = (
            "wg-quick's iptables NAT step failed inside the torrent namespace "
            "(this NAS kernel has no nft addrtype/comment). The appliance sets "
            "Table = off and adds the default route itself — recreate the container "
            "from a current image."
        )
        return f"{hint} {detail}".strip()[:2000]
    if returncode == 127 or "command not found" in lower:
        hint = (
            "WireGuard kernel module is not available and wg-quick could not run "
            "wireguard-go. Recreate the container from a current image, load WireGuard "
            "on the NAS, or switch the profile to OpenVPN."
        )
        return f"{hint} {detail}".strip()[:2000]
    return (detail or f"wg-quick/openvpn exited {returncode}")[:2000]


class VpnManager:
    def __init__(self, app_settings: Settings | None = None) -> None:
        self.settings = app_settings or settings
        self._last_error = ""
        self._active_wg_conf: Path | None = None

    @property
    def config_path(self) -> Path:
        return Path(self.settings.vpn_config_path)

    def status(self) -> dict[str, Any]:
        tunnel_up = self._tunnel_up()
        netns = self._netns_exists()
        isolated = bool(self.settings.vpn_enabled and netns and tunnel_up)
        supervisor = ProcessSupervisor.get()
        running: dict[str, bool] = {}
        unprotected: list[str] = []
        for name in sorted(VPN_TUNNELED_APPS):
            is_running = supervisor.status(name).value == "running"
            running[name] = is_running
            if self._unprotected(is_running, isolated):
                unprotected.append(name)
        payload = {
            "enabled": self.settings.vpn_enabled,
            "enforce": self.settings.vpn_enforce,
            "provider": self.settings.vpn_provider,
            "protocol": self.settings.vpn_protocol,
            "config_present": self.config_path.is_file(),
            "config_path": str(self.config_path),
            "tunnel_up": tunnel_up,
            "kill_switch": bool(self.settings.vpn_enabled),
            "netns": TORRENT_NETNS if os.name == "posix" else None,
            "netns_ready": netns,
            "platform_linux": self._is_linux(),
            "qbittorrent_running": running.get("qbittorrent", False),
            "qbittorrent_unprotected": "qbittorrent" in unprotected,
            "prowlarr_running": running.get("prowlarr", False),
            "prowlarr_unprotected": "prowlarr" in unprotected,
            "flaresolverr_running": running.get("flaresolverr", False),
            "flaresolverr_unprotected": "flaresolverr" in unprotected,
            "tunneled_apps": sorted(VPN_TUNNELED_APPS),
            "unprotected_apps": unprotected,
            "supported_providers": list(PROVIDERS),
            "usenet_bypasses_vpn": True,
            "last_error": self._last_error or "",
            "endpoint_hosts": self._endpoint_hosts(),
            "webui_proxy_ports": vpn_webui_proxy.listening_ports(),
        }
        return payload

    def wrap_torrent_command(self, cmd: list[str]) -> list[str]:
        return self.wrap_isolated_command(cmd)

    def wrap_isolated_command(self, cmd: list[str]) -> list[str]:
        """Run the process inside amm-torrent when VPN is enabled.

        Always prefix on Linux so a missing netns fails closed instead of leaking
        onto the house WAN.
        """
        if not self.settings.vpn_enabled:
            return cmd
        if not self._is_linux():
            return cmd
        if shutil.which("ip") is None:
            return cmd
        return ["ip", "netns", "exec", TORRENT_NETNS, *cmd]

    def assert_can_start_tunneled_app(self, name: str) -> None:
        """Kill switch only applies while the VPN switch is on.

        VPN off → qBittorrent / Prowlarr / Flaresolverr may start on the house network.
        VPN on (Linux) → they may start only when the tunnel namespace is up.
        """
        if name not in VPN_TUNNELED_APPS:
            return
        if not self.settings.vpn_enabled:
            return
        if not self._is_linux():
            logger.warning("VPN is enabled but network namespaces are Linux-only.")
            return
        if self._netns_exists() and self._tunnel_up():
            return
        raise VpnIsolationError(
            f"Refusing to start '{name}' off-VPN: the tunnel must be up "
            f"(netns {TORRENT_NETNS} with WireGuard/OpenVPN) while VPN is enabled. "
            "Turn the VPN switch off in Settings → Network to run on the house network."
        )

    def tunneled_apps_allowed(self) -> bool:
        """True when VPN is off (house network OK) or the Linux tunnel is up."""
        if not self.settings.vpn_enabled:
            return True
        if not self._is_linux():
            return True
        return self._netns_exists() and self._tunnel_up()

    def start(self) -> dict[str, Any]:
        if not self.config_path.is_file():
            return self._fail(f"VPN config missing: {self.config_path}")
        if self._is_linux():
            self._drop_stale_netns()
            self._ensure_resolvconf_shim()
            ns_error = self._ensure_netns()
            if ns_error:
                return self._fail(ns_error)
        proto = self.settings.vpn_protocol
        up_conf = self.config_path
        if proto == "wireguard":
            exe = shutil.which("wg-quick")
            if exe:
                try:
                    up_conf = self._prepared_wireguard_config()
                except OSError as exc:
                    return self._fail(f"Could not prepare WireGuard config: {exc}")
                inner = [exe, "up", str(up_conf)]
            else:
                inner = None
        else:
            exe = shutil.which("openvpn")
            inner = [exe, "--config", str(self.config_path), "--daemon"] if exe else None
        if not inner:
            return self._fail(f"{proto} tools are not installed on this host.")
        cmd = self.wrap_isolated_command(inner) if self._is_linux() else inner
        env = os.environ.copy()
        env["PATH"] = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
        wg_go = shutil.which("wireguard-go")
        if wg_go:
            env["WG_QUICK_USERSPACE_IMPLEMENTATION"] = wg_go
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=60, env=env)
            self._active_wg_conf = up_conf if proto == "wireguard" else None
            self._last_error = ""
            if self._is_linux():
                self._add_tunnel_default_routes()
                self._forward_local_ports()
                self._apply_netns_kill_switch()
                self._purge_stale_dns_underlay()
                self._write_netns_resolv(self._dns_for_netns())
            return {"status": "started", **self.status()}
        except subprocess.CalledProcessError as exc:
            return self._fail(vpn_start_failure_detail(exc.returncode, exc.stderr or "", exc.stdout or ""))
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            return self._fail(str(exc))

    def _fail(self, detail: str) -> dict[str, Any]:
        self._last_error = (detail or "VPN start failed.")[:2000]
        logger.error("VPN start failed: %s", self._last_error)
        return {"status": "error", "detail": self._last_error, **self.status()}

    def stop(self) -> dict[str, Any]:
        vpn_webui_proxy.stop_all()
        proto = self.settings.vpn_protocol
        if proto == "wireguard" and shutil.which("wg-quick"):
            down_conf = self._active_wg_conf if self._active_wg_conf and self._active_wg_conf.is_file() else self.config_path
            if down_conf.is_file():
                down = ["wg-quick", "down", str(down_conf)]
                # Settings may already clear vpn_enabled before stop(); still tear the
                # tunnel down inside the netns while it exists.
                if self._is_linux() and self._netns_exists() and shutil.which("ip"):
                    cmd = ["ip", "netns", "exec", TORRENT_NETNS, *down]
                else:
                    cmd = down
                subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
        self._active_wg_conf = None
        if self._is_linux():
            self._teardown_netns()
        return {"status": "stopped", **self.status()}

    def _unprotected(self, running: bool, isolated: bool) -> bool:
        if not running:
            return False
        if not self.settings.vpn_enabled:
            return False
        return not isolated

    def _ensure_netns(self) -> str | None:
        if shutil.which("ip") is None:
            return "iproute2 (`ip`) is required for VPN isolation."
        self._drop_stale_netns()
        if not self._netns_exists():
            Path("/var/run/netns").mkdir(parents=True, exist_ok=True)
            result = self._ip(["netns", "add", TORRENT_NETNS])
            if result.returncode != 0 and "File exists" not in (result.stderr or ""):
                return result.stderr.strip() or "Failed to create network namespace."
        self._ip(["link", "add", _VETH_HOST, "type", "veth", "peer", "name", _VETH_NS])
        self._ip(["link", "set", _VETH_NS, "netns", TORRENT_NETNS])
        self._ip(["addr", "add", f"{_NS_HOST_IP}/24", "dev", _VETH_HOST])
        self._ip(["link", "set", _VETH_HOST, "up"])
        self._ip(["netns", "exec", TORRENT_NETNS, "ip", "addr", "add", f"{_NS_PEER_IP}/24", "dev", _VETH_NS])
        self._ip(["netns", "exec", TORRENT_NETNS, "ip", "link", "set", _VETH_NS, "up"])
        self._ip(["netns", "exec", TORRENT_NETNS, "ip", "link", "set", "lo", "up"])
        self._write_netns_resolv()
        self._apply_host_veth_guard()
        self._apply_netns_kill_switch()
        # No default route via the veth: the only WAN path is the VPN interface.
        return None

    def _host_iptables(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        iptables = shutil.which("iptables")
        if iptables is None:
            return subprocess.CompletedProcess(args, 1, "", "iptables not found")
        try:
            return subprocess.run([iptables, *args], capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return subprocess.CompletedProcess(args, 1, "", str(exc))

    def _ns_iptables(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        iptables = shutil.which("iptables")
        ip = shutil.which("ip")
        if iptables is None or ip is None:
            return subprocess.CompletedProcess(args, 1, "", "iptables not found")
        try:
            return subprocess.run(
                [ip, "netns", "exec", TORRENT_NETNS, iptables, *args],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return subprocess.CompletedProcess(args, 1, "", str(exc))

    def _underlay_ips(self) -> list[str]:
        import socket

        hosts: list[str] = []
        try:
            if self.config_path.is_file():
                hosts = parse_vpn_underlay_hosts(self.config_path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            hosts = []
        ips: list[str] = []
        seen: set[str] = set()
        for host in hosts:
            resolved: list[str] = []
            if _is_dns_address(host) and ":" not in host:
                resolved = [host]
            else:
                try:
                    infos = socket.getaddrinfo(host, None, socket.AF_INET)
                    resolved = [item[4][0] for item in infos]
                except OSError:
                    resolved = []
            for ip in resolved:
                if ip not in seen:
                    seen.add(ip)
                    ips.append(ip)
        return ips

    def _endpoint_hosts(self) -> list[str]:
        try:
            if self.config_path.is_file():
                return parse_vpn_underlay_hosts(
                    self.config_path.read_text(encoding="utf-8", errors="replace")
                )
        except OSError:
            return []
        return []

    def _endpoint_ip_map(self) -> dict[str, str]:
        mapping: dict[str, str] = {}
        ips = self._underlay_ips()
        hosts = self._endpoint_hosts()
        if len(hosts) == 1 and ips:
            mapping[hosts[0]] = ips[0]
            mapping[hosts[0].lower()] = ips[0]
            return mapping
        import socket

        for host in hosts:
            if _is_dns_address(host) and ":" not in host:
                mapping[host] = host
                continue
            try:
                infos = socket.getaddrinfo(host, None, socket.AF_INET)
                ip = infos[0][4][0] if infos else ""
            except OSError:
                ip = ""
            if ip:
                mapping[host] = ip
                mapping[host.lower()] = ip
        return mapping

    def _profile_dns_servers(self) -> list[str]:
        try:
            if self.config_path.is_file():
                return parse_vpn_dns_servers(
                    self.config_path.read_text(encoding="utf-8", errors="replace")
                )
        except OSError:
            return []
        return []

    def _bootstrap_ips(self) -> list[str]:
        """Handshake endpoints that must use the house underlay.

        Do **not** pin public DNS (1.1.1.1 / 9.9.9.9) via the veth here: on
        Synology and similar hosts NAT/MASQUERADE into the underlay fails, so
        DNS must ride the tunnel default route instead.
        """
        return list(self._underlay_ips())

    def _dns_for_netns(self) -> list[str]:
        """Nameservers for amm-torrent (always reachable via the tunnel default)."""
        servers: list[str] = []
        seen: set[str] = set()
        for host in self._profile_dns_servers() + list(_FALLBACK_DNS):
            if host in seen or host.startswith("127."):
                continue
            seen.add(host)
            servers.append(host)
        return servers or list(_FALLBACK_DNS)

    def _prepared_wireguard_config(self) -> Path:
        raw = self.config_path.read_text(encoding="utf-8", errors="replace")
        rewritten = ensure_wireguard_table_off(
            rewrite_wireguard_endpoints(raw, self._endpoint_ip_map())
        )
        runtime_dir = Path("/run/amm-vpn")
        try:
            runtime_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            runtime_dir = Path(self.settings.config_dir) / "vpn" / ".run"
            runtime_dir.mkdir(parents=True, exist_ok=True)
        dest = runtime_dir / "wg0.conf"
        dest.write_text(rewritten if rewritten.endswith("\n") else rewritten + "\n", encoding="utf-8")
        try:
            dest.chmod(0o600)
        except OSError:
            pass
        return dest

    def _apply_host_veth_guard(self) -> None:
        """Forward only VPN handshake packets from amm-torrent; drop any other WAN leak."""
        dests = self._bootstrap_ips()
        established = [
            "FORWARD",
            "-i",
            _VETH_HOST,
            "-m",
            "conntrack",
            "--ctstate",
            "ESTABLISHED,RELATED",
            "-j",
            "ACCEPT",
        ]
        if self._host_iptables(["-C", *established]).returncode != 0:
            self._host_iptables(["-I", "FORWARD", "1", *established[1:]])
        for dest in dests:
            accept = ["FORWARD", "-i", _VETH_HOST, "-d", dest, "-j", "ACCEPT"]
            if self._host_iptables(["-C", *accept]).returncode != 0:
                self._host_iptables(["-I", "FORWARD", "1", "-i", _VETH_HOST, "-d", dest, "-j", "ACCEPT"])
            nat = [
                "-t",
                "nat",
                "-C",
                "POSTROUTING",
                "-s",
                f"{_NS_PEER_IP}/32",
                "-d",
                dest,
                "-j",
                "MASQUERADE",
            ]
            if self._host_iptables(nat).returncode != 0:
                self._host_iptables(
                    [
                        "-t",
                        "nat",
                        "-A",
                        "POSTROUTING",
                        "-s",
                        f"{_NS_PEER_IP}/32",
                        "-d",
                        dest,
                        "-j",
                        "MASQUERADE",
                    ]
                )
            self._ip(["netns", "exec", TORRENT_NETNS, "ip", "route", "replace", dest, "via", _NS_HOST_IP])
        # Older builds pinned public DNS via the underlay; drop those so queries use wg0.
        self._purge_stale_dns_underlay()
        drop = ["FORWARD", "-i", _VETH_HOST, "-j", "DROP"]
        if self._host_iptables(["-C", *drop]).returncode != 0:
            self._host_iptables(["-A", *drop])

    def _purge_stale_dns_underlay(self) -> None:
        """Remove underlay routes/NAT for public DNS left by older VPN setups."""
        for dest in _FALLBACK_DNS:
            self._host_iptables(["-D", "FORWARD", "-i", _VETH_HOST, "-d", dest, "-j", "ACCEPT"])
            self._host_iptables(
                [
                    "-t",
                    "nat",
                    "-D",
                    "POSTROUTING",
                    "-s",
                    f"{_NS_PEER_IP}/32",
                    "-d",
                    dest,
                    "-j",
                    "MASQUERADE",
                ]
            )
            if self._netns_exists():
                self._ip(["netns", "exec", TORRENT_NETNS, "ip", "route", "del", dest])

    def _apply_netns_kill_switch(self) -> None:
        """Drop any non-tunnel WAN from Prowlarr/qBittorrent/Flaresolverr."""
        if shutil.which("iptables") is None:
            logger.warning("iptables not found; cannot install the torrent VPN kill switch.")
            return
        self._ns_iptables(["-N", _KS_CHAIN])
        self._ns_iptables(["-F", _KS_CHAIN])
        # Replies to DNATed/proxied WebUI traffic must return even when the peer is a
        # Docker bridge address rather than 10.200.200.0/24.
        rules = [
            ["-A", _KS_CHAIN, "-m", "conntrack", "--ctstate", "ESTABLISHED,RELATED", "-j", "RETURN"],
            ["-A", _KS_CHAIN, "-m", "state", "--state", "ESTABLISHED,RELATED", "-j", "RETURN"],
            ["-A", _KS_CHAIN, "-o", "lo", "-j", "RETURN"],
            ["-A", _KS_CHAIN, "-d", "10.200.200.0/24", "-j", "RETURN"],
        ]
        for dest in self._bootstrap_ips():
            rules.append(["-A", _KS_CHAIN, "-d", dest, "-j", "RETURN"])
        rules.extend(
            [
                ["-A", _KS_CHAIN, "-o", "wg+", "-j", "RETURN"],
                ["-A", _KS_CHAIN, "-o", "tun+", "-j", "RETURN"],
                ["-A", _KS_CHAIN, "-j", "DROP"],
            ]
        )
        for spec in rules:
            result = self._ns_iptables(spec)
            if result.returncode != 0 and ("conntrack" in spec or "state" in spec):
                logger.debug("Kill switch reply rule skipped: %s", (result.stderr or "")[:180])
        if self._ns_iptables(["-C", "OUTPUT", "-j", _KS_CHAIN]).returncode != 0:
            self._ns_iptables(["-I", "OUTPUT", "1", "-j", _KS_CHAIN])
        self._ns_iptables(["-P", "FORWARD", "DROP"])

    def _write_netns_resolv(self, servers: list[str] | None = None) -> None:
        """Docker's 127.0.0.11 resolver is not reachable from amm-torrent."""
        if not servers:
            servers = list(_FALLBACK_DNS)
        path = Path(f"/etc/netns/{TORRENT_NETNS}/resolv.conf")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("".join(f"nameserver {item}\n" for item in servers), encoding="utf-8")
        except OSError as exc:
            logger.warning("Could not write %s: %s", path, exc)

    def _webui_ports(self) -> dict[str, int]:
        ports = dict(_DEFAULT_PORTS)
        try:
            from applications.catalog import ApplicationCatalog

            catalog = ApplicationCatalog(app_settings=self.settings)
            for name in VPN_TUNNELED_APPS:
                if catalog.has(name):
                    ports[name] = catalog.get(name).port
        except Exception:
            logger.debug("Using default VPN WebUI ports", exc_info=True)
        return ports

    def _teardown_netns(self) -> None:
        for dest in self._bootstrap_ips():
            self._host_iptables(["-D", "FORWARD", "-i", _VETH_HOST, "-d", dest, "-j", "ACCEPT"])
            self._host_iptables(
                [
                    "-t",
                    "nat",
                    "-D",
                    "POSTROUTING",
                    "-s",
                    f"{_NS_PEER_IP}/32",
                    "-d",
                    dest,
                    "-j",
                    "MASQUERADE",
                ]
            )
        self._host_iptables(["-D", "FORWARD", "-i", _VETH_HOST, "-j", "DROP"])
        self._ip(["link", "delete", _VETH_HOST])
        if self._netns_bind_path().exists():
            self._ip(["netns", "delete", TORRENT_NETNS])
            self._unlink_netns_bind()

    def _forward_local_ports(self) -> None:
        """Publish netns WebUIs on the main netns so Docker port maps work.

        Prefer a userspace TCP proxy (reliable with Synology/Docker userland
        proxies). Keep a light FORWARD accept so the proxy can reach the veth peer.
        """
        ports = self._webui_ports()
        ready = vpn_webui_proxy.ensure(ports.values(), dest_host=_NS_PEER_IP)
        if ready:
            logger.info("VPN WebUI proxies ready on ports %s", ", ".join(str(p) for p in ready))
        else:
            logger.warning("VPN WebUI proxies failed to bind; falling back to iptables DNAT.")
            self._forward_local_ports_dnat(ports)

        subprocess.run(
            ["sysctl", "-w", "net.ipv4.ip_forward=1"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        inbound = [
            "FORWARD",
            "-o",
            _VETH_HOST,
            "-d",
            _NS_PEER_IP,
            "-p",
            "tcp",
            "-j",
            "ACCEPT",
        ]
        if self._host_iptables(["-C", *inbound]).returncode != 0:
            result = self._host_iptables(["-I", "FORWARD", "1", *inbound[1:]])
            if result.returncode != 0:
                logger.warning("VPN WebUI forward rule failed: %s", (result.stderr or "")[:200])
        established = [
            "FORWARD",
            "-i",
            _VETH_HOST,
            "-m",
            "conntrack",
            "--ctstate",
            "ESTABLISHED,RELATED",
            "-j",
            "ACCEPT",
        ]
        if self._host_iptables(["-C", *established]).returncode != 0:
            self._host_iptables(["-I", "FORWARD", "1", *established[1:]])

    def _forward_local_ports_dnat(self, ports: dict[str, int]) -> None:
        iptables = shutil.which("iptables")
        if not iptables:
            logger.warning("iptables not found; VPN WebUIs may be unreachable.")
            return
        subprocess.run(
            ["sysctl", "-w", "net.ipv4.conf.all.route_localnet=1"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        for port in ports.values():
            dest = f"{_NS_PEER_IP}:{port}"
            dnat = ["-p", "tcp", "--dport", str(port), "-j", "DNAT", "--to-destination", dest]
            self._ensure_nat_insert("PREROUTING", dnat)
            self._ensure_nat_insert("OUTPUT", ["-d", "127.0.0.1", *dnat])
            self._ensure_nat_insert("OUTPUT", ["-o", "lo", *dnat])
        masq = ["-d", f"{_NS_PEER_IP}/32", "-p", "tcp", "-j", "MASQUERADE"]
        self._ensure_nat_insert("POSTROUTING", masq)

    def _ensure_nat(self, chain: str, spec: list[str]) -> None:
        check = ["-t", "nat", "-C", chain, *spec]
        if self._host_iptables(check).returncode == 0:
            return
        result = self._host_iptables(["-t", "nat", "-A", chain, *spec])
        if result.returncode != 0:
            logger.warning(
                "VPN WebUI NAT %s %s failed: %s",
                chain,
                " ".join(spec),
                (result.stderr or "")[:200],
            )

    def _ensure_nat_insert(self, chain: str, spec: list[str]) -> None:
        check = ["-t", "nat", "-C", chain, *spec]
        if self._host_iptables(check).returncode == 0:
            return
        result = self._host_iptables(["-t", "nat", "-I", chain, "1", *spec])
        if result.returncode != 0:
            logger.warning(
                "VPN WebUI NAT %s %s failed: %s",
                chain,
                " ".join(spec),
                (result.stderr or "")[:200],
            )

    def refresh_local_forwards(self) -> None:
        """Re-bind WebUI proxies while the tunnel is up (Docker may flush paths)."""
        if not self.settings.vpn_enabled or not self._is_linux():
            vpn_webui_proxy.stop_all()
            return
        if not self.tunneled_apps_allowed():
            return
        self._forward_local_ports()
        self._purge_stale_dns_underlay()
        self._write_netns_resolv(self._dns_for_netns())

    def _tunnel_interface_names(self) -> list[str]:
        result = self._ip(["netns", "exec", TORRENT_NETNS, "ip", "-o", "link", "show", "up"])
        names: list[str] = []
        for line in (result.stdout or "").splitlines():
            parts = line.split(":", 2)
            if len(parts) < 2:
                continue
            name = parts[1].strip().split("@", 1)[0]
            if name.startswith("wg") or name.startswith("tun"):
                names.append(name)
        return names

    def _add_tunnel_default_routes(self) -> None:
        """wg-quick Table=off does not install 0.0.0.0/0; we do it inside amm-torrent."""
        names = self._tunnel_interface_names()
        if not names:
            logger.warning("VPN interface came up but no wg/tun device was found in %s.", TORRENT_NETNS)
            return
        for name in names:
            v4 = self._ip(
                ["netns", "exec", TORRENT_NETNS, "ip", "-4", "route", "replace", "default", "dev", name]
            )
            if v4.returncode != 0:
                logger.warning("Could not add IPv4 default via %s: %s", name, (v4.stderr or "")[:200])
            self._ip(
                ["netns", "exec", TORRENT_NETNS, "ip", "-6", "route", "replace", "default", "dev", name]
            )

    def _tunnel_up(self) -> bool:
        """True only when a WireGuard/OpenVPN iface is up *inside* amm-torrent."""
        if not self._is_linux() or not self._netns_exists():
            return False
        if shutil.which("wg"):
            try:
                out = subprocess.run(
                    ["ip", "netns", "exec", TORRENT_NETNS, "wg", "show"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                )
                if out.returncode == 0 and out.stdout.strip():
                    return True
            except (OSError, subprocess.TimeoutExpired):
                pass
        return bool(self._tunnel_interface_names())

    def _netns_bind_path(self) -> Path:
        return Path(f"/var/run/netns/{TORRENT_NETNS}")

    def _netns_exists(self) -> bool:
        if not self._netns_bind_path().exists():
            return False
        result = self._ip(["netns", "exec", TORRENT_NETNS, "true"])
        return result.returncode == 0

    def _unlink_netns_bind(self) -> None:
        path = self._netns_bind_path()
        if not path.exists():
            return
        subprocess.run(["umount", str(path)], capture_output=True, text=True, timeout=5)
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("Could not remove stale netns bind %s: %s", path, exc)

    def _drop_stale_netns(self) -> None:
        if not self._netns_bind_path().exists():
            return
        if self._netns_exists():
            return
        logger.warning("Dropping stale torrent netns %s", TORRENT_NETNS)
        self._ip(["netns", "delete", TORRENT_NETNS])
        self._unlink_netns_bind()

    @staticmethod
    def _ensure_resolvconf_shim() -> None:
        if shutil.which("resolvconf"):
            return
        dest = Path("/usr/local/sbin/resolvconf")
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(
                "#!/bin/sh\n"
                "# wg-quick requires resolvconf when the profile has DNS=.\n"
                "# AMM already writes /etc/netns/<ns>/resolv.conf.\n"
                "exit 0\n",
                encoding="utf-8",
            )
            dest.chmod(0o755)
        except OSError as exc:
            logger.warning("Could not install resolvconf shim at %s: %s", dest, exc)

    @staticmethod
    def _is_linux() -> bool:
        return hasattr(os, "uname") and os.uname().sysname.lower() == "linux"

    @staticmethod
    def _ip(args: list[str]) -> subprocess.CompletedProcess[str]:
        ip = shutil.which("ip")
        if ip is None:
            return subprocess.CompletedProcess(args, 1, "", "ip not found")
        try:
            return subprocess.run([ip, *args], capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return subprocess.CompletedProcess(args, 1, "", str(exc))


vpn_manager = VpnManager()
