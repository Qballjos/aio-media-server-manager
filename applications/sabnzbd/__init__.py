from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

from applications.base import BaseApplication
from applications.install_helpers import child_python, create_venv, launch_argv, venv_bin, write_runner
from applications.manifest import AppCategory, AppManifest, AppTier, InstallMethod
from core.installer import AppInstaller, InstallResult

logger = logging.getLogger(__name__)

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
        runner = self.install_dir / "run-sabnzbd"
        if runner.is_file():
            return runner
        script = self.install_dir / "SABnzbd.py"
        if script.is_file():
            return script
        return super().executable_path()

    def is_installed(self) -> bool:
        script = self.install_dir / "SABnzbd.py"
        return script.is_file() and self._runtime_imports_ok(self._venv_python())

    def start_command(self) -> list[str]:
        self._ensure_runtime()
        self._write_runner()
        return super().start_command()

    def extra_env(self) -> dict[str, str]:
        lib = Path("/opt/python3.13/lib")
        if not lib.is_dir():
            return {}
        current = os.environ.get("LD_LIBRARY_PATH", "")
        if str(lib) in current.split(":"):
            return {"LD_LIBRARY_PATH": current} if current else {"LD_LIBRARY_PATH": str(lib)}
        return {"LD_LIBRARY_PATH": f"{lib}:{current}" if current else str(lib)}

    def _venv_python(self) -> Path:
        return venv_bin(self.install_dir / "venv", "python")

    def _runtime_imports_ok(self, python: Path) -> bool:
        if not python.is_file():
            return False
        probe = subprocess.run(
            [str(python), "-c", "import sabctools, cherrypy"],
            capture_output=True,
            text=True,
        )
        return probe.returncode == 0

    def _venv_matches_child(self, python: Path) -> bool:
        if not python.is_file():
            return False
        child = child_python()
        child_ver = subprocess.run(
            [child, "-c", "import sys; print(sys.version_info[:2])"],
            capture_output=True,
            text=True,
        )
        venv_ver = subprocess.run(
            [str(python), "-c", "import sys; print(sys.version_info[:2])"],
            capture_output=True,
            text=True,
        )
        return (
            child_ver.returncode == 0
            and venv_ver.returncode == 0
            and child_ver.stdout.strip() == venv_ver.stdout.strip()
        )

    def _ensure_runtime(self) -> Path:
        venv_python = self._venv_python()
        if self._venv_matches_child(venv_python) and self._runtime_imports_ok(venv_python):
            return venv_python
        venv_dir = self.install_dir / "venv"
        if venv_dir.exists():
            shutil.rmtree(venv_dir, ignore_errors=True)
        try:
            venv_dir = create_venv(self.install_dir, python=child_python())
        except subprocess.CalledProcessError as exc:
            detail = ((exc.stderr or exc.stdout or "") + str(exc))[-4000:]
            raise RuntimeError(f"SABnzbd virtualenv create failed: {detail}") from exc
        pip = venv_bin(venv_dir, "pip")
        requirements = self.install_dir / "requirements.txt"
        if requirements.is_file():
            _run_checked(
                [str(pip), "install", "-r", str(requirements)],
                "SABnzbd pip install",
            )
        return venv_bin(venv_dir, "python")

    def _write_runner(self) -> Path | None:
        script = self.install_dir / "SABnzbd.py"
        if not script.is_file():
            return None
        venv_python = self._venv_python()
        interpreter = str(venv_python) if venv_python.is_file() else child_python()
        lines = ["#!/bin/sh"]
        if Path("/opt/python3.13/lib").is_dir():
            lines.append(
                'export LD_LIBRARY_PATH="/opt/python3.13/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"'
            )
        lines.append(f'exec "{interpreter}" "{script}" "$@"')
        return write_runner(self.install_dir / "run-sabnzbd", lines)

    def install(self) -> InstallResult:
        installer = AppInstaller()
        result = installer.install_from_github(
            repo=self.github_repo,
            app_name=self.name,
            executable_name="SABnzbd.py",
            preferred_patterns=self.preferred_patterns(),
        )
        self._ensure_runtime()
        self._write_runner()
        self.post_install()
        return result

    def post_install(self) -> None:
        ini = self.config_dir / "sabnzbd.ini"
        if ini.exists():
            return
        from core.integrations.sabnzbd import write_bootstrap_ini
        from core.integrations.usenet import load_usenet_server
        from core.library_layout import LibraryLayout
        from core.settings import settings as app_settings
        from core.shared_credentials import shared_admin_credentials
        from core.integrations.credentials import set_application_api_key

        layout = LibraryLayout.from_settings(app_settings)
        shared = shared_admin_credentials()
        username = shared[0] if shared else ""
        password = shared[1] if shared else ""
        written = write_bootstrap_ini(
            ini,
            port=self.port,
            complete_dir=str(layout.complete),
            incomplete_dir=str(layout.incomplete),
            username=username,
            password=password,
            usenet=load_usenet_server(),
        )
        text = written.read_text(encoding="utf-8")
        for line in text.splitlines():
            if line.lower().startswith("api_key"):
                key = line.split("=", 1)[-1].strip().strip('"')
                if key:
                    set_application_api_key(self.name, key)
                break

    def build_start_command(self, executable: Path) -> list[str]:
        extra = [
            "--server",
            f"0.0.0.0:{self.port}",
            "--browser",
            "0",
            "--config-file",
            str(self.config_dir / "sabnzbd.ini"),
        ]
        if executable.suffix.lower() == ".py":
            interpreter = str(self._venv_python()) if self._venv_python().is_file() else child_python()
            return [interpreter, str(executable), *extra]
        return launch_argv(executable, extra)


def _run_checked(cmd: list[str], label: str) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()[-4000:]
        raise RuntimeError(f"{label} failed: {detail or f'exit {proc.returncode}'}")
