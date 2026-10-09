from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections import deque
from pathlib import Path

from applications.base import BaseApplication
from applications.install_helpers import node_bin, write_runner
from applications.manifest import AppCategory, AppManifest, AppTier, InstallMethod
from core.install_jobs import set_job
from core.installer import AppInstaller, InstallResult


MANIFEST = AppManifest(
    name="seerr",
    display_name="Seerr",
    description="Request management UI that connects to Sonarr, Radarr, Jellyfin, and Plex.",
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


def _install_progress(line: str) -> str | None:
    counts = re.search(
        r"Progress: resolved (\d{1,9}), reused (\d{1,9}), downloaded (\d{1,9}), added (\d{1,9})\b",
        line,
    )
    if counts:
        resolved, reused, downloaded, added = counts.groups()
        return (
            f"Installing dependencies: {downloaded} downloaded, {reused} cached, "
            f"{added} installed ({resolved} resolved)"
        )
    pages = re.search(
        r"Generating static pages(?: using \d{1,9} workers?)?\s*\((\d{1,9})\s*/\s*(\d{1,9})\)",
        line,
    )
    if pages:
        return f"Generating Seerr pages: {pages[1]}/{pages[2]}"
    for marker, message in (
        ("Creating an optimized production build", "Building Seerr's web interface…"),
        ("Compiled successfully", "Seerr web interface compiled…"),
        ("checking validity of types", "Checking Seerr's code and types…"),
        ("Running TypeScript", "Checking Seerr's code and types…"),
        ("Collecting page data", "Collecting Seerr page data…"),
        ("Finalizing page optimization", "Optimizing Seerr pages…"),
        ("Collecting build traces", "Collecting Seerr build files…"),
        ("tsc --project server/tsconfig.build.json", "Building Seerr's server…"),
    ):
        if marker in line:
            return message
    return None


def _limit_build_memory(config_path: Path) -> None:
    source = config_path.read_text(encoding="utf-8")
    marker = "export default nextConfig;"
    if source.count(marker) != 1:
        raise RuntimeError("Cannot apply Seerr build memory target: unrecognized next.config.ts")
    patch = """// AIO: keep the build's memory target low while other apps run.
const aioBuildMemoryLimit = nextConfig.experimental?.turbopackMemoryLimit;
nextConfig.experimental = {
  ...nextConfig.experimental,
  turbopackMemoryLimit:
    typeof aioBuildMemoryLimit === 'number' && Number.isFinite(aioBuildMemoryLimit) && aioBuildMemoryLimit > 0
      ? aioBuildMemoryLimit
      : 512 * 1024 * 1024,
};

"""
    if patch not in source:
        config_path.write_text(source.replace(marker, patch + marker), encoding="utf-8")


class SeerrApp(BaseApplication):
    manifest = MANIFEST

    def is_installed(self) -> bool:
        # Source metadata exists before the build; only a completed build creates the runner.
        return self.metadata_path().is_file() and any(
            (self.install_dir / name).is_file() for name in ("seerr", "run-seerr")
        )

    def extra_env(self) -> dict[str, str]:
        return {
            "NODE_ENV": "production",
            "PORT": str(self.port),
            "CONFIG_DIRECTORY": str(self.config_dir),
        }

    def install(self) -> InstallResult:
        self.require_host_arch()
        installer = AppInstaller()
        set_job(self.name, "installing", "Downloading Seerr source…")
        result = installer.install_from_github_source(
            self.github_repo,
            self.name,
            "package.json",
        )
        node = node_bin()
        if not node:
            raise FileNotFoundError("Node.js 22+ is required to install Seerr.")
        env = {**os.environ, "CI": "true", "CYPRESS_INSTALL_BINARY": "0"}
        set_job(self.name, "installing", "Preparing Seerr's package manager…")
        subprocess.run(
            ["corepack", "enable"],
            cwd=self.install_dir,
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        self._run_install_step(
            ["corepack", "prepare", "pnpm@10.24.0", "--activate"],
            env,
        )
        pnpm = shutil.which("pnpm") or "pnpm"
        set_job(self.name, "installing", "Installing Seerr dependencies…")
        self._run_install_step(
            [pnpm, "install", "--frozen-lockfile", "--reporter=append-only"],
            env,
        )
        set_job(self.name, "installing", "Building Seerr from source…")
        _limit_build_memory(self.install_dir / "next.config.ts")
        self._run_install_step([pnpm, "build"], {**env, "RAYON_NUM_THREADS": "1"})
        set_job(self.name, "installing", "Finishing Seerr installation…")
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

    def _run_install_step(self, command: list[str], env: dict[str, str]) -> None:
        tail: deque[str] = deque(maxlen=30)
        last_message = None
        with subprocess.Popen(
            command,
            cwd=self.install_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=env,
        ) as process:
            assert process.stdout is not None
            for line in process.stdout:
                tail.append(line[-2048:])
                # Only known counters and fixed phase labels may reach the dashboard.
                message = _install_progress(line)
                if message and message != last_message:
                    set_job(self.name, "installing", message)
                    last_message = message
            returncode = process.wait()
        if returncode:
            raise subprocess.CalledProcessError(returncode, command, output="".join(tail))

    def build_start_command(self, executable: Path) -> list[str]:
        return [str(executable)]
