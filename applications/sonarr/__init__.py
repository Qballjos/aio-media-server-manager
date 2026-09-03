from __future__ import annotations

from applications.arr import ArrApplication
from applications.manifest import AppCategory, AppManifest, AppTier, InstallMethod

MANIFEST = AppManifest(
    name="sonarr",
    display_name="Sonarr",
    description="TV series automation for Usenet and BitTorrent.",
    github_repo="Sonarr/Sonarr",
    upstream_url="https://github.com/Sonarr/Sonarr",
    tier=AppTier.CORE,
    category=AppCategory.AUTOMATION,
    default_port=8989,
    executable_name="Sonarr",
    supported_architectures=("x86_64", "arm64", "armv7"),
    install_method=InstallMethod.GITHUB_RELEASE,
    preferred_patterns=("linux",),
    optional_dependencies=("prowlarr", "sabnzbd", "qbittorrent"),
    health_path="/ping",
)


class SonarrApp(ArrApplication):
    manifest = MANIFEST
