from __future__ import annotations

from pathlib import Path

from applications.arr import ArrApplication
from applications.manifest import AppCategory, AppManifest, AppTier, InstallMethod
from core.vpn import vpn_manager

MANIFEST = AppManifest(
    name="prowlarr",
    display_name="Prowlarr",
    description="Indexer manager that syncs indexers to the *Arr applications.",
    github_repo="Prowlarr/Prowlarr",
    upstream_url="https://github.com/Prowlarr/Prowlarr",
    tier=AppTier.CORE,
    category=AppCategory.INDEXERS,
    default_port=9696,
    executable_name="Prowlarr",
    supported_architectures=("x86_64", "arm64", "armv7"),
    install_method=InstallMethod.GITHUB_RELEASE,
    preferred_patterns=("linux", "core"),
    health_path="/ping",
)


class ProwlarrApp(ArrApplication):
    manifest = MANIFEST

    def build_start_command(self, executable: Path) -> list[str]:
        return vpn_manager.wrap_isolated_command(super().build_start_command(executable))
