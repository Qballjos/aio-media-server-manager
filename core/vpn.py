"""
core/vpn.py — Optional VPN isolation for BitTorrent, Prowlarr, and Flaresolverr.

Usenet (SABnzbd/NZBGet) always stays on the host network. WireGuard runs in the
container's main network namespace (the pattern that works on Synology). Only
qBittorrent / Prowlarr / Flaresolverr are forced through wg0 via UID policy
routing — no nested netns and no iptables NAT.
"""

from __future__ import annotations

import logging
import os
import pwd
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from core.settings import Settings, settings
from core.supervisor import ProcessSupervisor
from core.vpn_proxy import vpn_webui_proxy
from core.vpn_relay import vpn_endpoint_relay

logger = logging.getLogger(__name__)

PROVIDERS = ("privadovpn", "mullvad", "protonvpn", "airvpn", "ivpn", "custom")
TORRENT_NETNS = "amm-torrent"
VPN_TUNNELED_APPS = frozenset({"qbittorrent", "prowlarr", "flaresolverr"})
MAX_VPN_CONFIG_BYTES = 256 * 1024
# WireGuard app isolation (main netns + policy routing). Matches Synology-safe VPN containers.
VPN_APP_USER = "ammvpn"
VPN_APP_UID = 910
VPN_APP_GID = 910
_VETH_HOST = "amm-veth-h"
_VETH_NS = "amm-veth-n"
_NS_HOST_IP = "10.200.200.1"
_NS_PEER_IP = "10.200.200.2"
TORRENT_BRIDGE_HOST = _NS_HOST_IP
_DEFAULT_PORTS = {"qbittorrent": 8081, "prowlarr": 9696, "flaresolverr": 8191}
_FALLBACK_DNS = ("1.1.1.1", "9.9.9.9")
_KS_CHAIN = "AMM-KS"
_UID_KS_CHAIN = "AMM-UID-KS"
_VPN_TABLE = 200
_VPN_UID_RULE_PRIORITY = 100
_VPN_RULE_PRIORITY = 100
_VPN_LOCAL_RULE_PRIORITY = 99
_VPN_UID_V6_BLACKHOLE_PRIORITY = 98


def unwrap_isolation_command(cmd: list[str] | None) -> list[str]:
    """Strip setpriv / netns / env wrappers so reclaim can match the real binary."""
    out = list(cmd or [])
    if len(out) >= 4 and out[0] == "ip" and out[1] == "netns" and out[2] == "exec":
        out = out[4:]
    if out and Path(out[0]).name == "setpriv":
        if "--" in out:
            out = out[out.index("--") + 1 :]
        else:
            idx = 1
            while idx < len(out) and out[idx].startswith("-"):
                idx += 1
            out = out[idx:]
    if out and Path(out[0]).name == "env":
        idx = 1
        while idx < len(out) and "=" in out[idx] and not out[idx].startswith("-"):
            idx += 1
        out = out[idx:]
    return out


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


def rewrite_wireguard_endpoint_host_port(text: str, host: str, port: str | int) -> str:
    """Force every Endpoint line to host:port (used for the local UDP relay)."""
    port_s = str(port)
    lines: list[str] = []
    for raw in text.splitlines(keepends=True):
        stripped = raw.split("#", 1)[0].strip()
        if not stripped.lower().startswith("endpoint"):
            lines.append(raw)
            continue
        prefix, sep, _rest = raw.partition("=")
        if not sep:
            prefix, sep, _rest = raw.partition(" ")
        newline = "\n" if raw.endswith("\n") else ""
        lines.append(f"{prefix}{sep} {host}:{port_s}{newline}")
    return "".join(lines)


def parse_wireguard_endpoint(text: str) -> tuple[str, int] | None:
    """Return the first Endpoint host/port from a WireGuard profile."""
    for raw in (text or "").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line.lower().startswith("endpoint"):
            continue
        _, _, rest = line.partition("=")
        if not rest.strip():
            _, _, rest = line.partition(" ")
        host, port = _split_endpoint(rest.strip())
        if not host:
            continue
        try:
            return host, int(port or "51820")
        except ValueError:
            return host, 51820
    return None


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


def sanitize_wireguard_runtime(text: str) -> str:
    """Drop DNS/hooks AMM already handles (or that break Synology iptables)."""
    drop = {"dns", "postup", "postdown", "preup", "predown"}
    out: list[str] = []
    for raw in text.splitlines(keepends=True):
        key = raw.split("#", 1)[0].strip().split("=", 1)[0].strip().lower()
        if key in drop:
            continue
        out.append(raw)
    return "".join(out)


def ensure_wireguard_persistent_keepalive(text: str, interval: int = 25) -> str:
    """Ensure each peer has PersistentKeepalive so handshakes start behind NAT/Table=off.

    With Table=off + UID routing, nothing sends traffic as root during start, so
    WireGuard never initiates a handshake unless keepalive is set.
    """
    if interval <= 0:
        return text
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    in_peer = False
    saw_keepalive = False

    def _flush_keepalive() -> None:
        nonlocal saw_keepalive
        if in_peer and not saw_keepalive:
            if out and not str(out[-1]).endswith("\n"):
                out[-1] = str(out[-1]) + "\n"
            out.append(f"PersistentKeepalive = {interval}\n")
            saw_keepalive = True

    for raw in lines:
        stripped = raw.split("#", 1)[0].strip()
        lower = stripped.lower()
        if lower.startswith("[") and lower.endswith("]"):
            _flush_keepalive()
            in_peer = lower == "[peer]"
            saw_keepalive = False
            out.append(raw)
            continue
        if in_peer and lower.startswith("persistentkeepalive"):
            newline = "\n" if raw.endswith("\n") else ""
            prefix, sep, _rest = raw.partition("=")
            if not sep:
                prefix, sep, _rest = raw.partition(" ")
            out.append(f"{prefix}{sep} {interval}{newline}")
            saw_keepalive = True
            continue
        out.append(raw)
    _flush_keepalive()
    return "".join(out)


def wireguard_covers_default_route(text: str) -> bool:
    """True when any peer AllowedIPs includes 0.0.0.0/0 (full-tunnel egress)."""
    for raw in (text or "").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line.lower().startswith("allowedips"):
            continue
        _, _, values = line.partition("=")
        if not values.strip():
            _, _, values = line.partition(" ")
        tokens = {
            item.strip().lower()
            for item in values.replace(";", ",").split(",")
            if item.strip()
        }
        if "0.0.0.0/0" in tokens:
            return True
    return False


def parse_wireguard_tunnel_address(text: str) -> str | None:
    """First IPv4 Address= from a WireGuard profile (without prefix length)."""
    for raw in (text or "").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line.lower().startswith("address"):
            continue
        _, _, values = line.partition("=")
        if not values.strip():
            _, _, values = line.partition(" ")
        for token in values.replace(";", ",").split(","):
            host = token.strip().split("/", 1)[0].strip()
            if host.count(".") == 3:
                return host
    return None


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
        self._cached_underlay_ips: list[str] | None = None
        self._handshake_cache: bool | None = None
        self._handshake_cache_at = 0.0
        self._wg_ifaces_cache: list[str] | None = None
        self._wg_ifaces_cache_at = 0.0

    def _invalidate_runtime_cache(self) -> None:
        self._handshake_cache = None
        self._handshake_cache_at = 0.0
        self._wg_ifaces_cache = None
        self._wg_ifaces_cache_at = 0.0

    @property
    def config_path(self) -> Path:
        return Path(self.settings.vpn_config_path)

    def status(self) -> dict[str, Any]:
        # Do not cache the full payload — settings like vpn_enabled must be live.
        # Expensive wg/iface probes are cached separately for ~2s.
        tunnel_up = self._tunnel_up()
        netns = self._netns_exists()
        isolated = bool(self.settings.vpn_enabled and tunnel_up)
        supervisor = ProcessSupervisor.get()
        running: dict[str, bool] = {}
        unprotected: list[str] = []
        for name in sorted(VPN_TUNNELED_APPS):
            is_running = supervisor.status(name).value == "running"
            running[name] = is_running
            if self._unprotected(is_running, isolated):
                unprotected.append(name)
        handshake_ok = (
            self._wireguard_handshake_fresh()
            if self.settings.vpn_protocol == "wireguard"
            else tunnel_up
        )
        return {
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
            "endpoint_ips": list(self._cached_underlay_ips or []),
            "webui_proxy_ports": vpn_webui_proxy.listening_ports(),
            "handshake_ok": handshake_ok,
            "isolation_mode": self.isolation_mode(),
            "vpn_app_uid": VPN_APP_UID if self.uses_uid_isolation() else None,
        }

    def isolation_mode(self) -> str:
        if not self.settings.vpn_enabled or not self._is_linux():
            return "off"
        if self.settings.vpn_protocol == "wireguard":
            return "uid"
        return "netns"

    def uses_uid_isolation(self) -> bool:
        return self.isolation_mode() == "uid"

    def uses_netns_isolation(self) -> bool:
        return self.isolation_mode() == "netns"

    def wrap_torrent_command(self, cmd: list[str]) -> list[str]:
        return self.wrap_isolated_command(cmd)

    def _vpn_app_gid(self) -> int:
        """Primary group for VPN-isolated apps — share PGID so downloads stay group-readable by Arr."""
        try:
            gid = int(self.settings.pgid)
        except (TypeError, ValueError):
            gid = VPN_APP_GID
        return gid if gid > 0 else VPN_APP_GID

    def wrap_isolated_command(self, cmd: list[str]) -> list[str]:
        """Force tunneled apps through the VPN without nested NAT on Synology."""
        if not self.settings.vpn_enabled:
            return cmd
        if not self._is_linux():
            return cmd
        if self.settings.vpn_protocol == "wireguard":
            if shutil.which("setpriv") is None:
                # Fail closed: never start torrent apps on the house WAN.
                logger.error("setpriv not found; refusing to start tunneled apps without WireGuard UID isolation.")
                raise VpnIsolationError(
                    "setpriv (util-linux) is required to isolate qBittorrent/Prowlarr/Flaresolverr "
                    "onto WireGuard. Install util-linux or turn VPN off in Settings → Network."
                )
            self._ensure_vpn_app_user()
            home = f"/tmp/{VPN_APP_USER}"
            gid = self._vpn_app_gid()
            return [
                "setpriv",
                f"--reuid={VPN_APP_UID}",
                f"--regid={gid}",
                "--clear-groups",
                "--",
                "env",
                f"HOME={home}",
                f"USER={VPN_APP_USER}",
                f"LOGNAME={VPN_APP_USER}",
                *cmd,
            ]
        if shutil.which("ip") is None:
            raise VpnIsolationError(
                "iproute2 (`ip`) is required for OpenVPN network-namespace isolation."
            )
        return ["ip", "netns", "exec", TORRENT_NETNS, *cmd]

    def assert_can_start_tunneled_app(self, name: str) -> None:
        """Kill switch only applies while the VPN switch is on."""
        if name not in VPN_TUNNELED_APPS:
            return
        if not self.settings.vpn_enabled:
            return
        if not self._is_linux():
            logger.warning("VPN is enabled but isolation is Linux-only.")
            return
        if self.tunneled_apps_allowed():
            self.prepare_tunneled_app(name)
            return
        raise VpnIsolationError(
            f"Refusing to start '{name}' off-VPN: WireGuard must have a live handshake "
            "while VPN is enabled. Turn the VPN switch off in Settings → Network to run "
            "on the house network."
        )

    def tunneled_apps_allowed(self) -> bool:
        """True when VPN is off (house network OK) or the tunnel data plane is up."""
        if not self.settings.vpn_enabled:
            return True
        if not self._is_linux():
            return True
        return self._tunnel_up()

    def prepare_tunneled_app(self, name: str) -> None:
        """Ensure config/data paths are writable by the VPN app UID."""
        if not self.uses_uid_isolation():
            return
        self._ensure_vpn_app_user()
        gid = self._vpn_app_gid()
        try:
            from applications.catalog import ApplicationCatalog

            if ApplicationCatalog(app_settings=self.settings).has(name):
                app = ApplicationCatalog(app_settings=self.settings).get(name)
                config_dir = Path(app.config_dir)
                self._chown_tree(config_dir, uid=VPN_APP_UID, gid=gid)
                self._strip_posix_acls(config_dir)
                self._chmod_tree(config_dir, dir_mode=0o755, file_mode=0o644)
                if not self._vpn_uid_can_write(config_dir, gid=gid):
                    # Synology ACL often blocks uid 910 even after chown; open the app config.
                    logger.warning(
                        "VPN uid %s still cannot write %s after chown; relaxing mode (Synology ACL).",
                        VPN_APP_UID,
                        config_dir,
                    )
                    self._chmod_tree(config_dir, dir_mode=0o777, file_mode=0o666)
                    self._strip_posix_acls(config_dir)
                    if not self._vpn_uid_can_write(config_dir, gid=gid):
                        logger.error(
                            "VPN uid %s cannot write %s. On Synology run: "
                            "sudo synoacltool -del %s (host path) then chown -R %s:%s that folder.",
                            VPN_APP_UID,
                            config_dir,
                            config_dir,
                            VPN_APP_UID,
                            gid,
                        )
        except Exception:
            logger.debug("Could not resolve config dir for %s", name, exc_info=True)
        # Downloads stay owned by PUID:PGID so Arr can import; VPN uid shares PGID.
        self._prepare_shared_download_tree(Path(self.settings.download_dir), gid=gid)

    def _vpn_uid_can_write(self, path: Path, *, gid: int) -> bool:
        if not path.is_dir():
            return False
        setpriv = shutil.which("setpriv")
        if not setpriv:
            return False
        probe = path / f".ammvpn_write_test_{VPN_APP_UID}"
        try:
            result = subprocess.run(
                [
                    setpriv,
                    f"--reuid={VPN_APP_UID}",
                    f"--regid={gid}",
                    "--clear-groups",
                    "--",
                    "sh",
                    "-c",
                    f"echo ok > '{probe}' && rm -f '{probe}'",
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            return result.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False

    def _strip_posix_acls(self, path: Path) -> None:
        setfacl = shutil.which("setfacl")
        if not setfacl or not path.exists():
            return
        try:
            subprocess.run(
                [setfacl, "-b", "-R", str(path)],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.debug("setfacl -b %s failed: %s", path, exc)

    def _chmod_tree(self, path: Path, *, dir_mode: int, file_mode: int) -> None:
        if not path.exists():
            return
        try:
            if path.is_dir():
                os.chmod(path, dir_mode)
            else:
                os.chmod(path, file_mode)
                return
        except OSError as exc:
            logger.debug("chmod %s failed: %s", path, exc)
        for root, dirs, files in os.walk(path):
            for name in dirs:
                try:
                    os.chmod(Path(root) / name, dir_mode)
                except OSError:
                    pass
            for name in files:
                try:
                    os.chmod(Path(root) / name, file_mode)
                except OSError:
                    pass

    def _prepare_shared_download_tree(self, path: Path, *, gid: int) -> None:
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.warning("Could not create download dir %s: %s", path, exc)
            return
        try:
            puid = int(self.settings.puid)
        except (TypeError, ValueError):
            puid = VPN_APP_UID
        # Owner stays PUID; group PGID with setgid so new files stay group-accessible.
        self._chown_tree(path, uid=puid, gid=gid, mode=0o2775)
        # VPN uid must be able to write into the tree even when some files are 644/755.
        self._ensure_group_writable(path)

    def _ensure_group_writable(self, path: Path) -> None:
        if not path.is_dir():
            return
        for root, dirs, files in os.walk(path):
            for name in dirs:
                target = Path(root) / name
                try:
                    mode = target.stat().st_mode
                    os.chmod(target, mode | 0o2770)
                except OSError:
                    pass
            for name in files:
                target = Path(root) / name
                try:
                    mode = target.stat().st_mode
                    os.chmod(target, mode | 0o660)
                except OSError:
                    pass

    def start(self) -> dict[str, Any]:
        if not self.config_path.is_file():
            return self._fail(f"VPN config missing: {self.config_path}")
        self._cached_underlay_ips = None
        proto = self.settings.vpn_protocol

        if proto == "wireguard":
            return self._start_wireguard_uid()

        # OpenVPN: legacy netns path (may not work on Synology without NAT).
        if self._is_linux():
            self._cached_underlay_ips = self._resolve_underlay_ips()
            self._drop_stale_netns()
            self._ensure_resolvconf_shim()
            ns_error = self._ensure_netns()
            if ns_error:
                return self._fail(ns_error)
        exe = shutil.which("openvpn")
        if not exe:
            return self._fail("openvpn is not installed on this host.")
        inner = [exe, "--config", str(self.config_path), "--daemon"]
        cmd = self.wrap_isolated_command(inner) if self._is_linux() else inner
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=60)
            self._active_wg_conf = None
            self._last_error = ""
            if self._is_linux():
                self._add_tunnel_default_routes()
                self._forward_local_ports()
                self._apply_netns_kill_switch()
                self._write_netns_resolv(self._dns_for_netns())
            self._invalidate_runtime_cache()
            return {"status": "started", **self.status()}
        except subprocess.CalledProcessError as exc:
            return self._fail(vpn_start_failure_detail(exc.returncode, exc.stderr or "", exc.stdout or ""))
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            return self._fail(str(exc))

    def _start_wireguard_uid(self) -> dict[str, Any]:
        """WireGuard in main netns + UID policy routing (Synology-safe, no iptables NAT)."""
        try:
            raw = self.config_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return self._fail(f"Could not read WireGuard config: {exc}")
        if not wireguard_covers_default_route(raw):
            return self._fail(
                "WireGuard AllowedIPs must include 0.0.0.0/0 so indexers and DNS "
                "can use the tunnel. Split-tunnel profiles are not supported."
            )
        self._cached_underlay_ips = self._resolve_underlay_ips()
        if not self._cached_underlay_ips:
            return self._fail(
                "Could not resolve the VPN Endpoint to an IP from the house network. "
                "Check DNS on the NAS or use a numeric Endpoint in the profile."
            )
        if shutil.which("setpriv") is None:
            return self._fail("setpriv (util-linux) is required for WireGuard app isolation.")
        self._ensure_vpn_app_user()

        # Tear down leftover nested-netns / relay experiments from older builds.
        vpn_endpoint_relay.stop()
        vpn_webui_proxy.stop_all()
        self._clear_uid_wireguard_routing()
        self._clear_main_wireguard_routing()
        if self._is_linux():
            self._teardown_netns()

        exe = shutil.which("wg-quick")
        if not exe:
            return self._fail("wireguard tools are not installed on this host.")
        try:
            up_conf = self._prepared_wireguard_config()
        except OSError as exc:
            return self._fail(f"Could not prepare WireGuard config: {exc}")
        self._wireguard_down_main(up_conf)
        env = os.environ.copy()
        env["PATH"] = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
        wg_go = shutil.which("wireguard-go")
        if wg_go:
            env["WG_QUICK_USERSPACE_IMPLEMENTATION"] = wg_go
        try:
            subprocess.run(
                [exe, "up", str(up_conf)],
                check=True,
                capture_output=True,
                text=True,
                timeout=60,
                env=env,
            )
        except subprocess.CalledProcessError as exc:
            return self._fail(vpn_start_failure_detail(exc.returncode, exc.stderr or "", exc.stdout or ""))
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            return self._fail(str(exc))

        self._active_wg_conf = up_conf
        # Teardown may have probed interfaces while none existed; drop that miss.
        self._wg_ifaces_cache = None
        self._wg_ifaces_cache_at = 0.0
        route_error = self._apply_uid_wireguard_routing()
        if route_error:
            self._wireguard_down_main(up_conf)
            self._clear_uid_wireguard_routing()
            return self._fail(route_error)
        if not self._wait_for_wireguard_handshake():
            self._wireguard_down_main(up_conf)
            self._clear_uid_wireguard_routing()
            return self._fail(
                "WireGuard interface is up but no handshake completed. "
                "Check the Privado profile, endpoint UDP reachability from the NAS, "
                "and that outbound UDP is not blocked."
            )
        self._last_error = ""
        for name in sorted(VPN_TUNNELED_APPS):
            self.prepare_tunneled_app(name)
        logger.info(
            "WireGuard up in main netns; torrent apps use uid %s via routing table %s",
            VPN_APP_UID,
            _VPN_TABLE,
        )
        self._invalidate_runtime_cache()
        return {"status": "started", **self.status()}

    def _fail(self, detail: str) -> dict[str, Any]:
        self._last_error = (detail or "VPN start failed.")[:2000]
        logger.error("VPN start failed: %s", self._last_error)
        self._invalidate_runtime_cache()
        return {"status": "error", "detail": self._last_error, **self.status()}

    def stop(self) -> dict[str, Any]:
        vpn_webui_proxy.stop_all()
        vpn_endpoint_relay.stop()
        proto = self.settings.vpn_protocol
        if proto == "wireguard" and shutil.which("wg-quick"):
            down_conf = (
                self._active_wg_conf
                if self._active_wg_conf and self._active_wg_conf.is_file()
                else self.config_path
            )
            self._wireguard_down_main(down_conf)
            self._wireguard_down_netns(down_conf)
        self._active_wg_conf = None
        self._cached_underlay_ips = None
        if self._is_linux():
            self._clear_uid_wireguard_routing()
            self._clear_main_wireguard_routing()
            self._teardown_netns()
        self._invalidate_runtime_cache()
        return {"status": "stopped", **self.status()}

    def _ensure_vpn_app_user(self) -> None:
        home = Path(f"/tmp/{VPN_APP_USER}")
        try:
            home.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        try:
            pwd.getpwnam(VPN_APP_USER)
        except KeyError:
            cmd = [
                "useradd",
                "-u",
                str(VPN_APP_UID),
                "-g",
                str(VPN_APP_GID) if self._group_exists(VPN_APP_GID) else "nogroup",
                "-M",
                "-d",
                str(home),
                "-s",
                "/usr/sbin/nologin",
                VPN_APP_USER,
            ]
            # Prefer creating the group first.
            subprocess.run(
                ["groupadd", "-g", str(VPN_APP_GID), VPN_APP_USER],
                capture_output=True,
                text=True,
                timeout=10,
            )
            cmd = [
                "useradd",
                "-u",
                str(VPN_APP_UID),
                "-g",
                str(VPN_APP_GID),
                "-M",
                "-d",
                str(home),
                "-s",
                "/usr/sbin/nologin",
                VPN_APP_USER,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode != 0 and "already exists" not in (result.stderr or "").lower():
                logger.warning("Could not create %s user: %s", VPN_APP_USER, (result.stderr or "")[:200])
        try:
            os.chown(home, VPN_APP_UID, VPN_APP_GID)
        except OSError:
            pass

    @staticmethod
    def _group_exists(gid: int) -> bool:
        import grp

        try:
            grp.getgrgid(gid)
            return True
        except KeyError:
            return False

    def _chown_tree(
        self,
        path: Path,
        *,
        uid: int = VPN_APP_UID,
        gid: int = VPN_APP_GID,
        mode: int | None = 0o755,
    ) -> None:
        if not path.exists():
            try:
                path.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                logger.warning("Could not create %s for VPN apps: %s", path, exc)
                return
        try:
            os.chown(path, uid, gid)
            if mode is not None:
                os.chmod(path, mode)
        except OSError as exc:
            logger.warning("chown/chmod %s -> %s:%s failed: %s", path, uid, gid, exc)
            # Fall back to recursive chown(1) which sometimes succeeds when os.chown fails.
            self._chown_cli(path, uid, gid)
            return
        if not path.is_dir():
            return
        for root, dirs, files in os.walk(path):
            for name in dirs + files:
                target = Path(root) / name
                try:
                    os.chown(target, uid, gid)
                    if mode is not None and target.is_dir():
                        os.chmod(target, mode)
                    elif mode is not None and target.is_file():
                        os.chmod(target, 0o644 if mode == 0o755 else (mode & 0o666))
                except OSError:
                    pass

    def _chown_cli(self, path: Path, uid: int, gid: int) -> None:
        chown = shutil.which("chown")
        if not chown:
            return
        try:
            result = subprocess.run(
                [chown, "-R", f"{uid}:{gid}", str(path)],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            if result.returncode != 0:
                logger.warning(
                    "chown -R %s:%s %s failed: %s",
                    uid,
                    gid,
                    path,
                    (result.stderr or result.stdout or "")[:200],
                )
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.warning("chown -R %s failed: %s", path, exc)

    def _apply_uid_wireguard_routing(self) -> str | None:
        ifaces = self._main_tunnel_interface_names()
        if not ifaces:
            return "WireGuard came up but no wg interface was found."
        wg = ifaces[0]
        result = self._ip(["route", "replace", "default", "dev", wg, "table", str(_VPN_TABLE)])
        if result.returncode != 0:
            return f"Could not install WireGuard default route: {(result.stderr or '')[:180]}"
        # Localhost / link-local always from main table for the VPN UID.
        self._ip(
            [
                "rule",
                "add",
                "uidrange",
                f"{VPN_APP_UID}-{VPN_APP_UID}",
                "lookup",
                "main",
                "suppress_prefixlength",
                "0",
                "priority",
                str(_VPN_UID_RULE_PRIORITY - 1),
            ]
        )
        rule = self._ip(
            [
                "rule",
                "add",
                "uidrange",
                f"{VPN_APP_UID}-{VPN_APP_UID}",
                "lookup",
                str(_VPN_TABLE),
                "priority",
                str(_VPN_UID_RULE_PRIORITY),
            ]
        )
        if rule.returncode != 0 and "File exists" not in (rule.stderr or ""):
            # suppress_prefixlength may be unsupported; fall back to a single rule.
            self._ip(
                [
                    "rule",
                    "del",
                    "uidrange",
                    f"{VPN_APP_UID}-{VPN_APP_UID}",
                    "lookup",
                    "main",
                    "suppress_prefixlength",
                    "0",
                    "priority",
                    str(_VPN_UID_RULE_PRIORITY - 1),
                ]
            )
            rule = self._ip(
                [
                    "rule",
                    "add",
                    "uidrange",
                    f"{VPN_APP_UID}-{VPN_APP_UID}",
                    "lookup",
                    str(_VPN_TABLE),
                    "priority",
                    str(_VPN_UID_RULE_PRIORITY),
                ]
            )
            if rule.returncode != 0 and "File exists" not in (rule.stderr or ""):
                return f"Could not install UID routing rule: {(rule.stderr or '')[:180]}"
        # Ensure VPN UID can still reach loopback services (Arr on 127.0.0.1).
        self._ip(["route", "replace", "127.0.0.0/8", "dev", "lo", "table", str(_VPN_TABLE)])
        # IPv4 policy routing does not cover IPv6 — blackhole IPv6 for the VPN UID
        # so Happy Eyeballs / DHT cannot leak the house address.
        self._apply_uid_ipv6_blackhole()
        self._apply_uid_output_kill_switch(wg)
        return None

    def _apply_uid_ipv6_blackhole(self) -> None:
        """Block all IPv6 from the VPN UID (IPv4 tunnel only)."""
        self._ip(
            [
                "-6",
                "rule",
                "del",
                "uidrange",
                f"{VPN_APP_UID}-{VPN_APP_UID}",
                "blackhole",
                "priority",
                str(_VPN_UID_V6_BLACKHOLE_PRIORITY),
            ]
        )
        result = self._ip(
            [
                "-6",
                "rule",
                "add",
                "uidrange",
                f"{VPN_APP_UID}-{VPN_APP_UID}",
                "blackhole",
                "priority",
                str(_VPN_UID_V6_BLACKHOLE_PRIORITY),
            ]
        )
        if result.returncode == 0 or "File exists" in (result.stderr or ""):
            return
        # Fallback: blackhole default in table 200 + uid lookup.
        self._ip(["-6", "route", "replace", "blackhole", "default", "table", str(_VPN_TABLE)])
        fallback = self._ip(
            [
                "-6",
                "rule",
                "add",
                "uidrange",
                f"{VPN_APP_UID}-{VPN_APP_UID}",
                "lookup",
                str(_VPN_TABLE),
                "priority",
                str(_VPN_UID_RULE_PRIORITY),
            ]
        )
        if fallback.returncode != 0 and "File exists" not in (fallback.stderr or ""):
            logger.warning(
                "Could not install IPv6 blackhole for VPN uid %s: %s",
                VPN_APP_UID,
                (result.stderr or fallback.stderr or "")[:180],
            )

    def _apply_uid_output_kill_switch(self, wg_iface: str) -> None:
        """Reject clear-net OUTPUT from the VPN UID (defense in depth beyond policy routing)."""
        for helper in (self._host_iptables, self._host_ip6tables):
            helper(["-N", _UID_KS_CHAIN])
            helper(["-F", _UID_KS_CHAIN])
            helper(["-A", _UID_KS_CHAIN, "-o", "lo", "-j", "RETURN"])
            helper(["-A", _UID_KS_CHAIN, "-o", "wg+", "-j", "RETURN"])
            helper(["-A", _UID_KS_CHAIN, "-o", "tun+", "-j", "RETURN"])
            if wg_iface and wg_iface not in {"wg+", "tun+"}:
                helper(["-A", _UID_KS_CHAIN, "-o", wg_iface, "-j", "RETURN"])
            reject = helper(
                ["-A", _UID_KS_CHAIN, "-j", "REJECT", "--reject-with", "icmp-net-unreachable"]
            )
            if reject.returncode != 0:
                # ip6tables may want icmp6-adm-prohibited
                helper(["-A", _UID_KS_CHAIN, "-j", "REJECT"])
            jump = ["OUTPUT", "-m", "owner", "--uid-owner", str(VPN_APP_UID), "-j", _UID_KS_CHAIN]
            if helper(["-C", *jump]).returncode != 0:
                result = helper(["-I", "OUTPUT", "1", *jump[1:]])
                if result.returncode != 0:
                    logger.warning(
                        "VPN UID OUTPUT kill switch unavailable (%s). "
                        "Install iptables owner match (xt_owner) for leak protection.",
                        (result.stderr or "")[:160],
                    )

    def _clear_uid_output_kill_switch(self) -> None:
        jump = ["OUTPUT", "-m", "owner", "--uid-owner", str(VPN_APP_UID), "-j", _UID_KS_CHAIN]
        for helper in (self._host_iptables, self._host_ip6tables):
            helper(["-D", *jump])
            helper(["-F", _UID_KS_CHAIN])
            helper(["-X", _UID_KS_CHAIN])

    def _clear_uid_wireguard_routing(self) -> None:
        self._clear_uid_output_kill_switch()
        self._ip(
            [
                "rule",
                "del",
                "uidrange",
                f"{VPN_APP_UID}-{VPN_APP_UID}",
                "lookup",
                str(_VPN_TABLE),
                "priority",
                str(_VPN_UID_RULE_PRIORITY),
            ]
        )
        self._ip(
            [
                "rule",
                "del",
                "uidrange",
                f"{VPN_APP_UID}-{VPN_APP_UID}",
                "lookup",
                "main",
                "suppress_prefixlength",
                "0",
                "priority",
                str(_VPN_UID_RULE_PRIORITY - 1),
            ]
        )
        self._ip(
            [
                "-6",
                "rule",
                "del",
                "uidrange",
                f"{VPN_APP_UID}-{VPN_APP_UID}",
                "blackhole",
                "priority",
                str(_VPN_UID_V6_BLACKHOLE_PRIORITY),
            ]
        )
        self._ip(
            [
                "-6",
                "rule",
                "del",
                "uidrange",
                f"{VPN_APP_UID}-{VPN_APP_UID}",
                "lookup",
                str(_VPN_TABLE),
                "priority",
                str(_VPN_UID_RULE_PRIORITY),
            ]
        )
        self._ip(["route", "flush", "table", str(_VPN_TABLE)])
        self._ip(["-6", "route", "flush", "table", str(_VPN_TABLE)])

    def _wireguard_down_main(self, conf: Path | None = None) -> None:
        target = conf if conf and conf.is_file() else self.config_path
        if not shutil.which("wg-quick") or not target.is_file():
            return
        subprocess.run(
            ["wg-quick", "down", str(target)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self._ip(["link", "delete", "wg0"])

    def _wireguard_down_netns(self, conf: Path | None = None) -> None:
        target = conf if conf and conf.is_file() else self.config_path
        if not shutil.which("wg-quick") or not target.is_file():
            return
        if self._is_linux() and self._netns_exists() and shutil.which("ip"):
            subprocess.run(
                ["ip", "netns", "exec", TORRENT_NETNS, "wg-quick", "down", str(target)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            self._ip(["netns", "exec", TORRENT_NETNS, "ip", "link", "delete", "wg0"])

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
        subprocess.run(
            ["sysctl", "-w", "net.ipv4.ip_forward=1"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        self._write_netns_resolv()
        # Kill switch + bridge routes are applied after the tunnel is up.
        return None

    def _host_iptables(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        iptables = shutil.which("iptables")
        if iptables is None:
            return subprocess.CompletedProcess(args, 1, "", "iptables not found")
        try:
            return subprocess.run([iptables, *args], capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return subprocess.CompletedProcess(args, 1, "", str(exc))

    def _host_ip6tables(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        ip6tables = shutil.which("ip6tables")
        if ip6tables is None:
            return subprocess.CompletedProcess(args, 1, "", "ip6tables not found")
        try:
            return subprocess.run([ip6tables, *args], capture_output=True, text=True, timeout=5)
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
        if self._cached_underlay_ips is not None:
            return list(self._cached_underlay_ips)
        return self._resolve_underlay_ips()

    def _resolve_underlay_ips(self) -> list[str]:
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

    def _prepared_wireguard_config(self, *, relay_port: int | None = None) -> Path:
        raw = self.config_path.read_text(encoding="utf-8", errors="replace")
        rewritten = ensure_wireguard_persistent_keepalive(
            ensure_wireguard_table_off(
                sanitize_wireguard_runtime(rewrite_wireguard_endpoints(raw, self._endpoint_ip_map()))
            )
        )
        # relay_port kept for API compatibility with older call sites; unused in UID mode.
        _ = relay_port
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

    def _apply_main_wireguard_routing(self) -> str | None:
        """Send torrent-netns traffic out wg0 in the main netns (policy routing)."""
        ifaces = self._main_tunnel_interface_names()
        if not ifaces:
            return "WireGuard came up but no wg interface was found in the main network namespace."
        wg = ifaces[0]
        self._ip(["route", "replace", "default", "dev", wg, "table", str(_VPN_TABLE)])
        # Keep LAN bridge (Prowlarr → Sonarr) on the main table.
        self._ip(
            [
                "rule",
                "add",
                "from",
                "10.200.200.0/24",
                "to",
                "10.200.200.0/24",
                "lookup",
                "main",
                "priority",
                str(_VPN_LOCAL_RULE_PRIORITY),
            ]
        )
        self._ip(
            [
                "rule",
                "add",
                "iif",
                _VETH_HOST,
                "lookup",
                str(_VPN_TABLE),
                "priority",
                str(_VPN_RULE_PRIORITY),
            ]
        )
        # wg peers only accept the tunnel Address=; SNAT bridge sources to it.
        tunnel_ip = None
        try:
            tunnel_ip = parse_wireguard_tunnel_address(
                self.config_path.read_text(encoding="utf-8", errors="replace")
            )
        except OSError:
            tunnel_ip = None
        if tunnel_ip:
            snat = [
                "-t",
                "nat",
                "-C",
                "POSTROUTING",
                "-s",
                "10.200.200.0/24",
                "-o",
                wg,
                "-j",
                "SNAT",
                "--to-source",
                tunnel_ip,
            ]
            if self._host_iptables(snat).returncode != 0:
                result = self._host_iptables(
                    [
                        "-t",
                        "nat",
                        "-A",
                        "POSTROUTING",
                        "-s",
                        "10.200.200.0/24",
                        "-o",
                        wg,
                        "-j",
                        "SNAT",
                        "--to-source",
                        tunnel_ip,
                    ]
                )
                if result.returncode != 0:
                    logger.warning(
                        "VPN SNAT to tunnel address %s failed (%s); trying MASQUERADE.",
                        tunnel_ip,
                        (result.stderr or "")[:120],
                    )
                    tunnel_ip = None
        if not tunnel_ip:
            masq = [
                "-t",
                "nat",
                "-C",
                "POSTROUTING",
                "-s",
                "10.200.200.0/24",
                "-o",
                wg,
                "-j",
                "MASQUERADE",
            ]
            if self._host_iptables(masq).returncode != 0:
                result = self._host_iptables(
                    [
                        "-t",
                        "nat",
                        "-A",
                        "POSTROUTING",
                        "-s",
                        "10.200.200.0/24",
                        "-o",
                        wg,
                        "-j",
                        "MASQUERADE",
                    ]
                )
                if result.returncode != 0:
                    return (
                        "Could not SNAT/MASQUERADE torrent traffic onto WireGuard "
                        f"({(result.stderr or 'unknown error')[:180]})."
                    )
        return None

    def _clear_main_wireguard_routing(self) -> None:
        self._ip(
            [
                "rule",
                "del",
                "iif",
                _VETH_HOST,
                "lookup",
                str(_VPN_TABLE),
                "priority",
                str(_VPN_RULE_PRIORITY),
            ]
        )
        self._ip(
            [
                "rule",
                "del",
                "from",
                "10.200.200.0/24",
                "to",
                "10.200.200.0/24",
                "lookup",
                "main",
                "priority",
                str(_VPN_LOCAL_RULE_PRIORITY),
            ]
        )
        self._ip(["route", "flush", "table", str(_VPN_TABLE)])
        for wg in self._main_tunnel_interface_names() or ["wg0"]:
            self._host_iptables(
                [
                    "-t",
                    "nat",
                    "-D",
                    "POSTROUTING",
                    "-s",
                    "10.200.200.0/24",
                    "-o",
                    wg,
                    "-j",
                    "MASQUERADE",
                ]
            )
            tunnel_ip = None
            try:
                tunnel_ip = parse_wireguard_tunnel_address(
                    self.config_path.read_text(encoding="utf-8", errors="replace")
                )
            except OSError:
                tunnel_ip = None
            if tunnel_ip:
                self._host_iptables(
                    [
                        "-t",
                        "nat",
                        "-D",
                        "POSTROUTING",
                        "-s",
                        "10.200.200.0/24",
                        "-o",
                        wg,
                        "-j",
                        "SNAT",
                        "--to-source",
                        tunnel_ip,
                    ]
                )
        for out_dev in ("wg+", "tun+"):
            self._host_iptables(["-D", "FORWARD", "-i", _VETH_HOST, "-o", out_dev, "-j", "ACCEPT"])
            self._host_iptables(
                [
                    "-D",
                    "FORWARD",
                    "-i",
                    out_dev,
                    "-o",
                    _VETH_HOST,
                    "-m",
                    "conntrack",
                    "--ctstate",
                    "ESTABLISHED,RELATED",
                    "-j",
                    "ACCEPT",
                ]
            )
        self._host_iptables(["-D", "FORWARD", "-i", _VETH_HOST, "-j", "DROP"])

    def _apply_torrent_bridge_default_route(self) -> None:
        """amm-torrent reaches the internet only via the host veth → wg0 policy route."""
        result = self._ip(
            [
                "netns",
                "exec",
                TORRENT_NETNS,
                "ip",
                "-4",
                "route",
                "replace",
                "default",
                "via",
                _NS_HOST_IP,
                "dev",
                _VETH_NS,
            ]
        )
        if result.returncode != 0:
            logger.warning(
                "Could not set torrent default via bridge: %s",
                (result.stderr or "")[:200],
            )

    def _apply_bridge_forward_guard(self) -> None:
        """Forward torrent traffic only onto wg/tun; drop clear-net leaks from the veth."""
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
        for out_dev in ("wg+", "tun+"):
            accept = ["FORWARD", "-i", _VETH_HOST, "-o", out_dev, "-j", "ACCEPT"]
            if self._host_iptables(["-C", *accept]).returncode != 0:
                self._host_iptables(["-I", "FORWARD", "1", *accept[1:]])
            back = [
                "FORWARD",
                "-i",
                out_dev,
                "-o",
                _VETH_HOST,
                "-m",
                "conntrack",
                "--ctstate",
                "ESTABLISHED,RELATED",
                "-j",
                "ACCEPT",
            ]
            if self._host_iptables(["-C", *back]).returncode != 0:
                self._host_iptables(["-I", "FORWARD", "1", *back[1:]])
        drop = ["FORWARD", "-i", _VETH_HOST, "-j", "DROP"]
        if self._host_iptables(["-C", *drop]).returncode != 0:
            self._host_iptables(["-A", *drop])

    def _apply_host_veth_guard(self) -> None:
        """Compatibility wrapper: WireGuard uses bridge forward guard after wg is up."""
        if self.settings.vpn_protocol == "wireguard" and self._main_tunnel_interface_names():
            self._apply_bridge_forward_guard()
            return
        # OpenVPN / legacy underlay path for handshake endpoints.
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
                result = self._host_iptables(
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
                if result.returncode != 0:
                    logger.warning(
                        "VPN underlay MASQUERADE for %s failed: %s",
                        dest,
                        (result.stderr or "")[:200],
                    )
            self._ip(["netns", "exec", TORRENT_NETNS, "ip", "route", "replace", dest, "via", _NS_HOST_IP])
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
        """Drop any non-bridge WAN from Prowlarr/qBittorrent/Flaresolverr."""
        if shutil.which("iptables") is None:
            logger.warning("iptables not found; cannot install the torrent VPN kill switch.")
            return
        self._ns_iptables(["-N", _KS_CHAIN])
        self._ns_iptables(["-F", _KS_CHAIN])
        rules = [
            ["-A", _KS_CHAIN, "-m", "conntrack", "--ctstate", "ESTABLISHED,RELATED", "-j", "RETURN"],
            ["-A", _KS_CHAIN, "-m", "state", "--state", "ESTABLISHED,RELATED", "-j", "RETURN"],
            ["-A", _KS_CHAIN, "-o", "lo", "-j", "RETURN"],
            # Bridge to main netns (WebUI peers, Sonarr/Radarr, and policy-routed WAN).
            ["-A", _KS_CHAIN, "-d", "10.200.200.0/24", "-j", "RETURN"],
            ["-A", _KS_CHAIN, "-o", _VETH_NS, "-j", "RETURN"],
            # Legacy OpenVPN path may still have tun/wg inside the netns.
            ["-A", _KS_CHAIN, "-o", "wg+", "-j", "RETURN"],
            ["-A", _KS_CHAIN, "-o", "tun+", "-j", "RETURN"],
            ["-A", _KS_CHAIN, "-j", "DROP"],
        ]
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
        content = "".join(f"nameserver {item}\n" for item in servers)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.is_file():
                try:
                    if path.read_text(encoding="utf-8") == content:
                        return
                except OSError:
                    pass
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_text(content, encoding="utf-8")
            os.replace(tmp, path)
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

    def _main_tunnel_interface_names(self) -> list[str]:
        now = time.monotonic()
        if self._wg_ifaces_cache is not None and (now - self._wg_ifaces_cache_at) < 2.0:
            return list(self._wg_ifaces_cache)
        names = self._discover_main_tunnel_interfaces()
        # Never cache a miss — teardown probes before wg-quick up and would
        # hide the interface for the next 2s ("no wg interface was found").
        if names:
            self._wg_ifaces_cache = names
            self._wg_ifaces_cache_at = now
        return list(names)

    def _discover_main_tunnel_interfaces(self) -> list[str]:
        names: list[str] = []
        wg = shutil.which("wg")
        if wg:
            try:
                out = subprocess.run(
                    [wg, "show", "interfaces"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                    check=False,
                )
                if out.returncode == 0:
                    for token in (out.stdout or "").split():
                        if token and token not in names:
                            names.append(token)
            except (OSError, subprocess.TimeoutExpired):
                pass
        if names:
            return names
        # Prefer "up", then any link — userspace wg can briefly report DOWN.
        for args in (["-o", "link", "show", "up"], ["-o", "link", "show"]):
            result = self._ip(args)
            for line in (result.stdout or "").splitlines():
                parts = line.split(":", 2)
                if len(parts) < 2:
                    continue
                name = parts[1].strip().split("@", 1)[0]
                if (name.startswith("wg") or name.startswith("tun")) and name not in names:
                    names.append(name)
            if names:
                break
        return names

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
        """Table=off does not install 0.0.0.0/0; add default via wg/tun inside amm-torrent."""
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

    def _wireguard_handshake_fresh(self, max_age_seconds: int = 180) -> bool:
        """True when wg in the main netns reports a recent peer handshake."""
        now_mono = time.monotonic()
        if self._handshake_cache is not None and (now_mono - self._handshake_cache_at) < 2.0:
            return self._handshake_cache
        if not shutil.which("wg"):
            self._handshake_cache = False
            self._handshake_cache_at = now_mono
            return False
        try:
            out = subprocess.run(
                ["wg", "show", "all", "latest-handshakes"],
                capture_output=True,
                text=True,
                timeout=3,
            )
        except (OSError, subprocess.TimeoutExpired):
            self._handshake_cache = False
            self._handshake_cache_at = now_mono
            return False
        if out.returncode != 0:
            self._handshake_cache = False
            self._handshake_cache_at = now_mono
            return False
        now = time.time()
        fresh = False
        for line in (out.stdout or "").splitlines():
            parts = line.split()
            if len(parts) < 3:
                continue
            try:
                ts = int(parts[-1])
            except ValueError:
                continue
            if ts > 0 and (now - ts) <= max_age_seconds:
                fresh = True
                break
        self._handshake_cache = fresh
        self._handshake_cache_at = now_mono
        return fresh

    def _wait_for_wireguard_handshake(self, timeout_seconds: float = 25.0) -> bool:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if self._wireguard_handshake_fresh():
                return True
            time.sleep(1.0)
        return self._wireguard_handshake_fresh()

    def _tunnel_up(self) -> bool:
        """True when the tunnel data plane is usable for torrent apps."""
        if not self._is_linux():
            return False
        if self.settings.vpn_protocol == "wireguard":
            return bool(self._main_tunnel_interface_names()) and self._wireguard_handshake_fresh()
        if not self._netns_exists():
            return False
        return bool(self._tunnel_interface_names())

    def refresh_local_forwards(self) -> None:
        """Keep UID routes / netns proxies healthy while VPN is up."""
        if not self.settings.vpn_enabled or not self._is_linux():
            vpn_webui_proxy.stop_all()
            vpn_endpoint_relay.stop()
            return
        if not self.tunneled_apps_allowed():
            return
        if self.uses_uid_isolation():
            vpn_webui_proxy.stop_all()
            vpn_endpoint_relay.stop()
            self._apply_uid_wireguard_routing()
            return
        self._forward_local_ports()
        self._write_netns_resolv(self._dns_for_netns())

    def tunnel_interface_name(self) -> str | None:
        """Primary WireGuard/tun device used for torrent isolation, if any."""
        if self.settings.vpn_protocol == "wireguard":
            names = self._main_tunnel_interface_names()
            return names[0] if names else None
        names = self._tunnel_interface_names()
        return names[0] if names else None

    def reclaim_clearnet_tunneled_processes(self) -> list[str]:
        """Kill tunneled-app processes that are not running as the VPN UID.

        Leftover house-network copies (started before VPN, or after a failed
        reclaim) are the most common real-world IP leak with WireGuard UID mode.
        """
        if not self.uses_uid_isolation():
            return []
        try:
            import psutil
        except ImportError:
            return []
        from applications.catalog import ApplicationCatalog

        catalog = ApplicationCatalog(app_settings=self.settings)
        leaked: list[str] = []
        for name in sorted(VPN_TUNNELED_APPS):
            if not catalog.has(name):
                continue
            plugin = catalog.get(name)
            if not plugin.is_installed():
                continue
            exe = plugin.executable_path()
            if exe is None:
                continue
            token_path = str(exe)
            exe_name = exe.name
            mine = {os.getpid(), os.getppid()}
            found_wrong_uid = False
            try:
                processes = list(psutil.process_iter(["pid", "cmdline", "uids"]))
            except (psutil.Error, PermissionError, OSError):
                processes = []
            for proc in processes:
                pid = proc.info.get("pid")
                if not pid or pid in mine:
                    continue
                cmdline = proc.info.get("cmdline") or []
                joined = " ".join(cmdline)
                if token_path not in joined and exe_name not in joined:
                    continue
                # Ignore unrelated processes that only mention the name in args.
                if not any(token_path in part or part.endswith(exe_name) for part in cmdline):
                    continue
                uids = proc.info.get("uids")
                real_uid = getattr(uids, "real", None) if uids is not None else None
                if real_uid is None:
                    try:
                        real_uid = proc.uids().real
                    except (psutil.Error, AttributeError):
                        continue
                if int(real_uid) == VPN_APP_UID:
                    continue
                found_wrong_uid = True
                try:
                    logger.error(
                        "Killing clearnet %s PID %s (uid %s; expected VPN uid %s)",
                        name,
                        pid,
                        real_uid,
                        VPN_APP_UID,
                    )
                    proc.terminate()
                    try:
                        proc.wait(timeout=3)
                    except psutil.TimeoutExpired:
                        proc.kill()
                except (psutil.Error, OSError):
                    continue
            # Do not call reclaim_leftover_processes here — it is UID-blind and would
            # SIGTERM the correctly isolated VPN UID processes every isolation tick.
            if found_wrong_uid:
                leaked.append(name)
        return leaked

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
