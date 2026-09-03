from __future__ import annotations

from pathlib import Path

from applications.base import BaseApplication
from applications.manifest import AppCategory, AppManifest, AppTier, InstallMethod

MANIFEST = AppManifest(
    name="seerr",
    display_name="Seerr",
    description="Request management UI that talks to Sonarr, Radarr, and the media server.",
    github_repo="seerr-team/seerr",
    upstream_url="https://github.com/seerr-team/seerr",
    tier=AppTier.CORE,
    category=AppCategory.REQUESTS,
    default_port=5055,
    executable_name="seerr",
    supported_architectures=("x86_64", "arm64"),
    install_method=InstallMethod.GITHUB_RELEASE,
    preferred_patterns=("linux",),
    optional_dependencies=("sonarr", "radarr", "jellyfin"),
    health_path="/api/v1/status",
)


class SeerrApp(BaseApplication):
    manifest = MANIFEST

    def extra_env(self) -> dict[str, str]:
        return {
            "NODE_ENV": "production",
            "PORT": str(self.port),
            "CONFIG_DIRECTORY": str(self.config_dir),
        }

    def build_start_command(self, executable: Path) -> list[str]:
        return [str(executable)]
