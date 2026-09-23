from __future__ import annotations

import subprocess
from pathlib import Path

from applications.base import BaseApplication
from applications.install_helpers import create_venv, venv_bin, write_runner
from applications.manifest import AppCategory, AppManifest, AppTier, InstallMethod
from core.installer import AppInstaller, InstallResult


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
    install_method=InstallMethod.GITHUB_RELEASE,
    preferred_patterns=(r"-src\.tar\.gz$",),
    health_path="/api?mode=version&output=json",
)


class SabnzbdApp(BaseApplication):
    manifest = MANIFEST

    def executable_path(self) -> Path | None:
        runner = self.install_dir / "sabnzbd"
        if runner.is_file():
            return runner
        script = self.install_dir / "SABnzbd.py"
        if script.is_file():
            return script
        return super().executable_path()

    def install(self) -> InstallResult:
        installer = AppInstaller()
        result = installer.install_from_github(
            repo=self.github_repo,
            app_name=self.name,
            executable_name="SABnzbd.py",
            preferred_patterns=self.preferred_patterns(),
        )
        venv_dir = create_venv(self.install_dir)
        pip = venv_bin(venv_dir, "pip")
        requirements = self.install_dir / "requirements.txt"
        if requirements.is_file():
            subprocess.run(
                [str(pip), "install", "-r", str(requirements)],
                check=True,
                capture_output=True,
                text=True,
            )
        python = venv_bin(venv_dir, "python")
        script = self.install_dir / "SABnzbd.py"
        runner = self.install_dir / "sabnzbd"
        write_runner(
            runner,
            [
                "#!/bin/sh",
                f'exec "{python}" "{script}" "$@"',
            ],
        )
        self.post_install()
        return result

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
