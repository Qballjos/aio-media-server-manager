from __future__ import annotations

import logging
from pathlib import Path
from typing import Sequence

from applications.base import BaseApplication
from applications.manifest import AppCategory, AppManifest, AppTier, InstallMethod
from applications.qbittorrent.webui import ensure_vpn_network_interface, ensure_webui_localhost_access
from core.installer.arch import PlatformArch, detect_system_arch, host_arch_filename_token
from core.vpn import vpn_manager

logger = logging.getLogger(__name__)

MANIFEST = AppManifest(
    name="qbittorrent",
    display_name="qBittorrent",
    description="BitTorrent client with VueTorrent WebUI and API (qbittorrent-nox).",
    github_repo="userdocs/qbittorrent-nox-static",
    upstream_url="https://github.com/qbittorrent/qBittorrent",
    tier=AppTier.CORE,
    category=AppCategory.DOWNLOADING,
    default_port=8081,
    executable_name="qbittorrent-nox",
    supported_architectures=("x86_64", "arm64", "armv7"),
    install_method=InstallMethod.GITHUB_RELEASE,
    preferred_patterns=("qbittorrent-nox",),
    health_path="/api/v2/app/version",
)


class QBittorrentApp(BaseApplication):
    """
    Uses statically linked official qBittorrent-nox builds.

    Upstream qBittorrent does not publish Linux binaries; the catalog tracks
    the official project URL while installing verified nox-static release assets.
    VueTorrent is installed by default as the alternative WebUI.
    """

    manifest = MANIFEST

    def preferred_patterns(self) -> Sequence[str]:
        arch = detect_system_arch()
        if arch == PlatformArch.UNKNOWN:
            return ()
        token = host_arch_filename_token(arch)
        return (rf"{token}.*qbittorrent-nox",)

    def post_install(self) -> None:
        from applications.qbittorrent.vuetorrent import ensure_vuetorrent

        try:
            ensure_vuetorrent(self.config_dir)
        except Exception:
            # Stock WebUI still works if GitHub is unreachable during install.
            logger.warning(
                "VueTorrent default install failed; qBittorrent will use the stock WebUI until it succeeds.",
                exc_info=True,
            )

    def build_start_command(self, executable: Path) -> list[str]:
        username, password = "", ""
        try:
            from core.integrations.qbittorrent import target_webui_credentials

            username, password = target_webui_credentials()
            if username == "admin" and password == "adminadmin":
                username, password = "", ""
        except Exception:
            username, password = "", ""
        from applications.qbittorrent.vuetorrent import alternative_ui_root, ensure_vuetorrent

        try:
            ensure_vuetorrent(self.config_dir)
        except Exception:
            logger.warning(
                "VueTorrent not ready; starting qBittorrent with the stock WebUI.",
                exc_info=True,
            )

        ensure_webui_localhost_access(
            self.config_dir,
            username=username,
            password=password,
            alternative_ui_root=alternative_ui_root(self.config_dir),
        )
        # Prefer the WireGuard/tun device so trackers/peers never bind the LAN NIC.
        iface = vpn_manager.tunnel_interface_name() if vpn_manager.settings.vpn_enabled else None
        ensure_vpn_network_interface(self.config_dir, iface)
        cmd = [
            str(executable),
            f"--webui-port={self.port}",
            f"--profile={self.config_dir}",
            "--confirm-legal-notice",
        ]
        return vpn_manager.wrap_torrent_command(cmd)
