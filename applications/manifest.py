"""
applications/manifest.py — Catalog metadata types for application plugins.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Sequence


class AppTier(str, enum.Enum):
    CORE = "core"
    RECOMMENDED = "recommended"
    OPTIONAL = "optional"
    EXPERIMENTAL = "experimental"


class AppCategory(str, enum.Enum):
    DOWNLOADING = "downloading"
    AUTOMATION = "automation"
    INDEXERS = "indexers"
    SUBTITLES = "subtitles"
    MEDIA = "media"
    REQUESTS = "requests"
    OPTIMIZATION = "optimization"
    MAINTENANCE = "maintenance"


class InstallMethod(str, enum.Enum):
    GITHUB_RELEASE = "github_release"
    PYPI = "pypi"
    OFFICIAL_BINARY = "official_binary"
    NODE_BUNDLE = "node_bundle"


# Typical Servarr-stack adoption (higher = more popular). Unlisted apps use tier.
_POPULARITY_RANK: dict[str, int] = {
    "sonarr": 100,
    "radarr": 99,
    "prowlarr": 98,
    "jellyfin": 96,
    "plex": 95,
    "qbittorrent": 94,
    "sabnzbd": 93,
    "seerr": 90,
    "nzbget": 86,
    "bazarr": 85,
    "lidarr": 80,
    "unpackerr": 76,
    "recyclarr": 74,
    "tautulli": 70,
    "profilarr": 66,
    "neutarr": 64,
    "cleanuparr": 58,
    "maintainerr": 54,
    "kometa": 52,
    "autobrr": 48,
    "mylar3": 40,
}

_TIER_POPULARITY = {
    AppTier.CORE: 70,
    AppTier.RECOMMENDED: 50,
    AppTier.OPTIONAL: 30,
    AppTier.EXPERIMENTAL: 10,
}


def popularity_rank(name: str, tier: AppTier) -> int:
    return _POPULARITY_RANK.get(name, _TIER_POPULARITY.get(tier, 0))


@dataclass(frozen=True)
class AppManifest:
    """Declarative metadata for one catalog entry."""

    name: str
    display_name: str
    description: str
    github_repo: str
    upstream_url: str
    tier: AppTier
    category: AppCategory
    default_port: int
    executable_name: str
    supported_architectures: tuple[str, ...]
    install_method: InstallMethod
    preferred_patterns: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    optional_dependencies: tuple[str, ...] = ()
    health_path: str = "/ping"
    config_subdir: str = ""
    data_subdir: str = ""
    daemon: bool = True
    tags: Sequence[str] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "github_repo": self.github_repo,
            "upstream_url": self.upstream_url,
            "tier": self.tier.value,
            "category": self.category.value,
            "default_port": self.default_port,
            "executable_name": self.executable_name,
            "supported_architectures": list(self.supported_architectures),
            "install_method": self.install_method.value,
            "preferred_patterns": list(self.preferred_patterns),
            "dependencies": list(self.dependencies),
            "optional_dependencies": list(self.optional_dependencies),
            "health_path": self.health_path,
            "config_directory": self.config_subdir or self.name,
            "data_directory": self.data_subdir or self.name,
            "daemon": self.daemon,
            "popularity": popularity_rank(self.name, self.tier),
        }
