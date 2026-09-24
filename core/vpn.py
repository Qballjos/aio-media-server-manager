"""
core/vpn.py — Optional VPN isolation for BitTorrent, Prowlarr, and Flaresolverr.

Usenet (SABnzbd/NZBGet) always stays on the host network. When VPN is enabled
on Linux, qBittorrent, Prowlarr, and Flaresolverr run inside the `amm-torrent`
netns so their egress uses the tunnel only. Local WebUIs are DNAT'd from 127.0.0.1.
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


class VpnManager:
    def __init__(self, app_settings: Settings | None = None) -> None:
        self.settings = app_settings or settings

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
            "kill_switch": self.settings.vpn_enforce,
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
        }
        return payload

    def wrap_torrent_command(self, cmd: list[str]) -> list[str]:
        return self.wrap_isolated_command(cmd)

    def wrap_isolated_command(self, cmd: list[str]) -> list[str]:
        """Prefix a command with `ip netns exec` when the isolation netns exists."""
        if not self.settings.vpn_enabled:
            return cmd
        if not self._is_linux():
            return cmd
        if shutil.which("ip") is None:
            return cmd
        if not self._netns_exists():
            logger.warning(
                "VPN is enabled but netns %s is missing; not wrapping %s",
                TORRENT_NETNS,
                cmd[:1],
            )
            return cmd
        return ["ip", "netns", "exec", TORRENT_NETNS, *cmd]

    def assert_can_start_tunneled_app(self, name: str) -> None:
        if name not in VPN_TUNNELED_APPS:
            return
        if not self.settings.vpn_enabled or not self.settings.vpn_enforce:
            return
        if not self._is_linux():
            logger.warning("VPN enforce is set but network namespaces are Linux-only.")
            return
        if self._netns_exists() and self._tunnel_up():
            return
        raise VpnIsolationError(
            f"Refusing to start '{name}' off-VPN: enable the tunnel first "
            f"(netns {TORRENT_NETNS} with WireGuard/OpenVPN up)."
        )

    def start(self) -> dict[str, Any]:
        if not self.config_path.is_file():
            return {"status": "error", "detail": f"VPN config missing: {self.config_path}"}
        if self._is_linux():
            ns_error = self._ensure_netns()
            if ns_error:
                return {"status": "error", "detail": ns_error, **self.status()}
        proto = self.settings.vpn_protocol
        if proto == "wireguard":
            exe = shutil.which("wg-quick")
            inner = [exe, "up", str(self.config_path)] if exe else None
        else:
            exe = shutil.which("openvpn")
            inner = [exe, "--config", str(self.config_path), "--daemon"] if exe else None
        if not inner:
            return {"status": "error", "detail": f"{proto} tools are not installed on this host."}
        cmd = self.wrap_isolated_command(inner) if self._is_linux() else inner
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=30)
            if self._is_linux():
                self._forward_local_ports()
            return {"status": "started", **self.status()}
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
            logger.warning("VPN start failed: %s", exc)
            return {"status": "error", "detail": str(exc), **self.status()}

    def stop(self) -> dict[str, Any]:
        proto = self.settings.vpn_protocol
        if proto == "wireguard" and shutil.which("wg-quick") and self.config_path.is_file():
            down = ["wg-quick", "down", str(self.config_path)]
            subprocess.run(
                self.wrap_isolated_command(down) if self._is_linux() else down,
                capture_output=True,
                text=True,
                timeout=30,
            )
        if self._is_linux():
            self._teardown_netns()
        return {"status": "stopped", **self.status()}

    def _unprotected(self, running: bool, isolated: bool) -> bool:
        if not running:
            return False
        if not self.settings.vpn_enforce:
            return False
        return not isolated

    def _ensure_netns(self) -> str | None:
        if shutil.which("ip") is None:
            return "iproute2 (`ip`) is required for VPN isolation."
        if not self._netns_exists():
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
        # No default route via the veth: the only WAN path is the VPN interface.
        return None

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
        self._ip(["link", "delete", _VETH_HOST])
        if self._netns_exists():
            self._ip(["netns", "delete", TORRENT_NETNS])

    def _forward_local_ports(self) -> None:
        iptables = shutil.which("iptables")
        if not iptables:
            logger.warning("iptables not found; VPN WebUIs may be unreachable on 127.0.0.1.")
            return
        subprocess.run(
            ["sysctl", "-w", "net.ipv4.conf.all.route_localnet=1"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        for port in self._webui_ports().values():
            rule = [
                iptables,
                "-t",
                "nat",
                "-C",
                "OUTPUT",
                "-o",
                "lo",
                "-p",
                "tcp",
                "--dport",
                str(port),
                "-j",
                "DNAT",
                "--to-destination",
                f"{_NS_PEER_IP}:{port}",
            ]
            exists = subprocess.run(rule, capture_output=True, text=True, timeout=5)
            if exists.returncode == 0:
                continue
            add = list(rule)
            add[4] = "-A"
            subprocess.run(add, capture_output=True, text=True, timeout=5)

    def _tunnel_up(self) -> bool:
        if self._is_linux() and self._netns_exists() and shutil.which("wg"):
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
        if shutil.which("wg"):
            try:
                out = subprocess.run(["wg", "show"], capture_output=True, text=True, timeout=3)
                if out.returncode == 0 and out.stdout.strip():
                    return True
            except (OSError, subprocess.TimeoutExpired):
                pass
        for name in ("tun0", "wg0", "utun0"):
            if Path(f"/sys/class/net/{name}").exists() or Path(f"/dev/{name}").exists():
                return True
        return False

    def _netns_exists(self) -> bool:
        return Path(f"/var/run/netns/{TORRENT_NETNS}").exists()

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
