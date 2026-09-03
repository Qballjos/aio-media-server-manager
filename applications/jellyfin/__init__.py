from __future__ import annotations

from pathlib import Path

from applications.base import BaseApplication
from applications.manifest import AppCategory, AppManifest, AppTier, InstallMethod
from core.settings import settings

MANIFEST = AppManifest(
    name="jellyfin",
    display_name="Jellyfin",
    description="Free media server for movies, TV, and music with optional hardware transcoding.",
    github_repo="jellyfin/jellyfin",
    upstream_url="https://github.com/jellyfin/jellyfin",
    tier=AppTier.CORE,
    category=AppCategory.MEDIA,
    default_port=8096,
    executable_name="jellyfin",
    supported_architectures=("x86_64", "arm64"),
    install_method=InstallMethod.GITHUB_RELEASE,
    preferred_patterns=("linux", "amd64", "arm64"),
    health_path="/health",
    config_subdir="jellyfin/config",
    data_subdir="jellyfin/data",
)


class JellyfinApp(BaseApplication):
    manifest = MANIFEST

    def extra_env(self) -> dict[str, str]:
        cache = settings.cache_dir / "jellyfin"
        logs = settings.config_dir / "logs" / "jellyfin"
        cache.mkdir(parents=True, exist_ok=True)
        logs.mkdir(parents=True, exist_ok=True)
        return {
            "JELLYFIN_DATA_DIR": str(self.data_dir),
            "JELLYFIN_CONFIG_DIR": str(self.config_dir),
            "JELLYFIN_LOG_DIR": str(logs),
            "JELLYFIN_CACHE_DIR": str(cache),
        }

    def build_start_command(self, executable: Path) -> list[str]:
        webdir = self.install_dir / "jellyfin-web"
        cmd = [
            str(executable),
            "--datadir",
            str(self.data_dir),
            "--configdir",
            str(self.config_dir),
            "--logdir",
            str(settings.config_dir / "logs" / "jellyfin"),
            "--cachedir",
            str(settings.cache_dir / "jellyfin"),
        ]
        if webdir.is_dir():
            cmd.extend(["--webdir", str(webdir)])
        return cmd
