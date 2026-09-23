"""
core/vpn.py — Optional torrent-only VPN (WireGuard/OpenVPN) with kill-switch status.
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


class VpnManager:
    def __init__(self, app_settings: Settings | None = None) -> None:
        self.settings = app_settings or settings

    @property
    def config_path(self) -> Path:
        return Path(self.settings.vpn_config_path)

    def status(self) -> dict[str, Any]:
        tunnel_up = self._tunnel_up()
        qbit_running = ProcessSupervisor.get().status("qbittorrent").value == "running"
        unprotected = bool(
            self.settings.vpn_enforce and qbit_running and (not tunnel_up or not self.settings.vpn_enabled)
        )
        return {
            "enabled": self.settings.vpn_enabled,
            "enforce": self.settings.vpn_enforce,
            "provider": self.settings.vpn_provider,
            "protocol": self.settings.vpn_protocol,
            "config_present": self.config_path.is_file(),
            "config_path": str(self.config_path),
            "tunnel_up": tunnel_up,
            "kill_switch": self.settings.vpn_enforce,
            "netns": TORRENT_NETNS if os.name == "posix" else None,
            "platform_linux": os.uname().sysname.lower() == "linux" if hasattr(os, "uname") else False,
            "qbittorrent_running": qbit_running,
            "qbittorrent_unprotected": unprotected,
            "supported_providers": list(PROVIDERS),
            "usenet_bypasses_vpn": True,
        }

    def wrap_torrent_command(self, cmd: list[str]) -> list[str]:
        """Prefix qBittorrent with `ip netns exec` when the Linux netns exists."""
        if not self.settings.vpn_enabled:
            return cmd
        if os.uname().sysname.lower() != "linux" if hasattr(os, "uname") else True:
            return cmd
        if shutil.which("ip") is None:
            return cmd
        if not self._netns_exists():
            return cmd
        return ["ip", "netns", "exec", TORRENT_NETNS, *cmd]

    def start(self) -> dict[str, Any]:
        if not self.config_path.is_file():
            return {"status": "error", "detail": f"VPN config missing: {self.config_path}"}
        proto = self.settings.vpn_protocol
        if proto == "wireguard":
            exe = shutil.which("wg-quick")
            cmd = [exe, "up", str(self.config_path)] if exe else None
        else:
            exe = shutil.which("openvpn")
            cmd = [exe, "--config", str(self.config_path), "--daemon"] if exe else None
        if not cmd:
            return {"status": "error", "detail": f"{proto} tools are not installed on this host."}
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=30)
            return {"status": "started", **self.status()}
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
            logger.warning("VPN start failed: %s", exc)
            return {"status": "error", "detail": str(exc), **self.status()}

    def stop(self) -> dict[str, Any]:
        proto = self.settings.vpn_protocol
        if proto == "wireguard" and shutil.which("wg-quick") and self.config_path.is_file():
            subprocess.run(
                ["wg-quick", "down", str(self.config_path)],
                capture_output=True,
                text=True,
                timeout=30,
            )
        return {"status": "stopped", **self.status()}

    def _tunnel_up(self) -> bool:
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
        ns = Path(f"/var/run/netns/{TORRENT_NETNS}")
        return ns.exists()


vpn_manager = VpnManager()
