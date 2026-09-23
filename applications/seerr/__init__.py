from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from applications.base import BaseApplication
from applications.install_helpers import node_bin, write_runner
from applications.manifest import AppCategory, AppManifest, AppTier, InstallMethod
from core.installer import AppInstaller, InstallResult


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
    install_method=InstallMethod.NODE_BUNDLE,
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

    def install(self) -> InstallResult:
        installer = AppInstaller()
        result = installer.install_from_github_source(
            self.github_repo,
            self.name,
            "package.json",
        )
        node = node_bin()
        if not node:
            raise FileNotFoundError("Node.js 22+ is required to install Seerr.")
        env = {**os.environ, "CI": "true", "CYPRESS_INSTALL_BINARY": "0"}
        subprocess.run(
            ["corepack", "enable"],
            cwd=self.install_dir,
            check=False,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["corepack", "prepare", "pnpm@10.24.0", "--activate"],
            cwd=self.install_dir,
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
        pnpm = shutil.which("pnpm") or "pnpm"
        subprocess.run(
            [pnpm, "install", "--frozen-lockfile"],
            cwd=self.install_dir,
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
        subprocess.run(
            [pnpm, "build"],
            cwd=self.install_dir,
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
        runner = self.install_dir / "seerr"
        write_runner(
            runner,
            [
                "#!/bin/sh",
                f'cd "{self.install_dir}"',
                f'export NODE_ENV=production',
                f'export PORT="{self.port}"',
                f'export CONFIG_DIRECTORY="{self.config_dir}"',
                f'exec "{node}" dist/index.js "$@"',
            ],
        )
        self.post_install()
        return result

    def build_start_command(self, executable: Path) -> list[str]:
        return [str(executable)]
