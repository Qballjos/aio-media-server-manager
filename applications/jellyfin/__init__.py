from __future__ import annotations

import logging
import re
from pathlib import Path

import requests

from applications.base import BaseApplication
from applications.manifest import AppCategory, AppManifest, AppTier, InstallMethod
from core.installer.arch import detect_system_arch
from core.installer.installer import AppInstaller, InstallResult
from core.settings import settings

logger = logging.getLogger(__name__)

JELLYFIN_LINUX_REPO = "https://repo.jellyfin.org/files/server/linux"
_ARCH_MAP = {"x86_64": "amd64", "arm64": "arm64"}
_ARCHIVE_RE = re.compile(
    r"jellyfin_([0-9][0-9A-Za-z.\-]*)-(amd64|arm64)\.tar\.(xz|gz)",
    re.IGNORECASE,
)

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
    # GitHub releases for jellyfin/jellyfin no longer attach Linux binaries.
    install_method=InstallMethod.OFFICIAL_BINARY,
    health_path="/health",
    config_subdir="jellyfin/config",
    data_subdir="jellyfin/data",
)


def jellyfin_repo_arch(host_arch: str | None = None) -> str:
    arch = host_arch or detect_system_arch().value
    mapped = _ARCH_MAP.get(arch)
    if mapped is None:
        raise RuntimeError(f"Jellyfin portable Linux builds are not published for {arch}.")
    return mapped


def pick_jellyfin_archive(listing_text: str, repo_arch: str) -> tuple[str, str]:
    """Return (filename, version) from a repo.jellyfin.org directory listing."""
    matches = [
        (match.group(0), match.group(1), match.group(3).lower())
        for match in _ARCHIVE_RE.finditer(listing_text)
        if match.group(2).lower() == repo_arch
    ]
    if not matches:
        raise RuntimeError(f"No Jellyfin portable archive found for {repo_arch} in repository listing.")
    matches.sort(key=lambda item: (0 if item[2] == "xz" else 1, item[1]))
    filename, version, _ext = matches[0]
    return filename, version


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
            "--http-port",
            str(self.port),
        ]
        webdir = self._webdir()
        if webdir is not None:
            cmd.extend(["--webdir", str(webdir)])
        return cmd

    def install(self) -> InstallResult:
        installer = AppInstaller()
        repo_arch = jellyfin_repo_arch()
        listing_url = f"{JELLYFIN_LINUX_REPO}/latest-stable/{repo_arch}/"
        logger.info("Resolving Jellyfin portable archive from %s", listing_url)
        response = requests.get(listing_url, timeout=30)
        response.raise_for_status()
        filename, version = pick_jellyfin_archive(response.text, repo_arch)
        url = f"{listing_url}{filename}"
        return installer.install_from_url(
            url=url,
            app_name=self.name,
            executable_name=self.executable_name,
            version=version,
        )

    def _webdir(self) -> Path | None:
        direct = self.install_dir / "jellyfin-web"
        if direct.is_dir():
            return direct
        if not self.install_dir.exists():
            return None
        for candidate in self.install_dir.rglob("jellyfin-web"):
            if candidate.is_dir():
                return candidate
        return None
