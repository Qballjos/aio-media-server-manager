from __future__ import annotations

from applications.arr import ArrApplication
from applications.manifest import AppCategory, AppManifest, AppTier, InstallMethod

MANIFEST = AppManifest(
    name="radarr",
    display_name="Radarr",
    description="Movie automation for Usenet and BitTorrent.",
    github_repo="Radarr/Radarr",
    upstream_url="https://github.com/Radarr/Radarr",
    tier=AppTier.CORE,
    category=AppCategory.AUTOMATION,
    default_port=7878,
    executable_name="Radarr",
    supported_architectures=("x86_64", "arm64", "armv7"),
    install_method=InstallMethod.GITHUB_RELEASE,
    preferred_patterns=("linux",),
    optional_dependencies=("prowlarr", "sabnzbd", "qbittorrent"),
    health_path="/ping",
)


class RadarrApp(ArrApplication):
    manifest = MANIFEST
