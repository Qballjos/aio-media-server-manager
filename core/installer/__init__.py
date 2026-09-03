"""
core/installer — Application Installer Package

Provides architecture detection, GitHub release querying, streaming downloads
with hash validation, multi-format archive extraction, and transactional
directory activation.
"""

from core.installer.arch import (
    PlatformArch,
    PlatformOS,
    detect_system_arch,
    detect_system_os,
    matches_arch_pattern,
    score_asset_match,
)
from core.installer.extractor import ArchiveExtractor, ExtractionSecurityError
from core.installer.github import GitHubRateLimitError, GitHubReleaseClient
from core.installer.installer import AppInstaller, InstallResult

__all__ = [
    "PlatformArch",
    "PlatformOS",
    "detect_system_arch",
    "detect_system_os",
    "matches_arch_pattern",
    "score_asset_match",
    "ArchiveExtractor",
    "ExtractionSecurityError",
    "GitHubReleaseClient",
    "GitHubRateLimitError",
    "AppInstaller",
    "InstallResult",
]
