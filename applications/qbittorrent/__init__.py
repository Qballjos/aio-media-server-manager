from __future__ import annotations

from pathlib import Path

from applications.base import BaseApplication
from applications.manifest import AppCategory, AppManifest, AppTier, InstallMethod
from applications.qbittorrent.webui import ensure_webui_localhost_access
from core.vpn import vpn_manager

MANIFEST = AppManifest(
    name="qbittorrent",
    display_name="qBittorrent",
    description="BitTorrent client with the official WebUI and API (qbittorrent-nox).",
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
    """

    manifest = MANIFEST

    def build_start_command(self, executable: Path) -> list[str]:
        username, password = "", ""
        try:
            from core.integrations.qbittorrent import target_webui_credentials

            username, password = target_webui_credentials()
            if username == "admin" and password == "adminadmin":
                username, password = "", ""
        except Exception:
            username, password = "", ""
        from applications.qbittorrent.vuetorrent import alternative_ui_root

        ensure_webui_localhost_access(
            self.config_dir,
            username=username,
            password=password,
            alternative_ui_root=alternative_ui_root(self.config_dir),
        )
        cmd = [
            str(executable),
            f"--webui-port={self.port}",
            f"--profile={self.config_dir}",
            "--confirm-legal-notice",
        ]
        return vpn_manager.wrap_torrent_command(cmd)
