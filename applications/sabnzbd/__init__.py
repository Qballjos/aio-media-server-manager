from __future__ import annotations

from pathlib import Path

from applications.base import BaseApplication
from applications.manifest import AppCategory, AppManifest, AppTier, InstallMethod

MANIFEST = AppManifest(
    name="sabnzbd",
    display_name="SABnzbd",
    description="Usenet downloader with a web interface, categories, and post-processing.",
    github_repo="sabnzbd/sabnzbd",
    upstream_url="https://github.com/sabnzbd/sabnzbd",
    tier=AppTier.CORE,
    category=AppCategory.DOWNLOADING,
    default_port=8085,
    executable_name="sabnzbd",
    supported_architectures=("x86_64", "arm64", "armv7"),
    install_method=InstallMethod.PYPI,
    health_path="/api?mode=version&output=json",
)


class SabnzbdApp(BaseApplication):
    manifest = MANIFEST

    def executable_path(self) -> Path | None:
        venv_bin = self.install_dir / "venv" / "bin" / "sabnzbd"
        if venv_bin.is_file():
            return venv_bin
        return super().executable_path()

    def build_start_command(self, executable: Path) -> list[str]:
        return [
            str(executable),
            "--server",
            f"0.0.0.0:{self.port}",
            "--browser",
            "0",
            "--config-file",
            str(self.config_dir / "sabnzbd.ini"),
        ]
