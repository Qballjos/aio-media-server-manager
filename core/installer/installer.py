"""
core/installer/installer.py — Transactional Application Installer

Coordinates:
  1. Architecture & platform resolution
  2. Asset discovery and download streaming with checksum verification
  3. Safe archive extraction into an isolated candidate directory
  4. Executable verification and permission enforcement
  5. Atomic directory activation with rollback capabilities
  6. Storage ownership application (PUID/PGID)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

import requests

from core.installer.arch import PlatformArch, PlatformOS, detect_system_arch, detect_system_os
from core.installer.extractor import ArchiveExtractor
from core.installer.github import GitHubReleaseClient
from core.settings import Settings, settings
from core.storage import StorageManager

logger = logging.getLogger(__name__)


@dataclass
class InstallResult:
    """Details of a successfully completed installation."""

    app_name: str
    version: str
    install_dir: Path
    executable_path: Path
    asset_name: str
    sha256: str
    installed_at: float


class AppInstaller:
    """
    Transactional application installer for downloading, verifying, and activating
    native application binaries.
    """

    def __init__(
        self,
        app_settings: Settings = settings,
        github_client: GitHubReleaseClient | None = None,
    ) -> None:
        self.settings = app_settings
        self.github_client = github_client or GitHubReleaseClient(token=app_settings.github_token)
        self.storage_manager = StorageManager(app_settings)

    # ------------------------------------------------------------------
    # High-level install workflows
    # ------------------------------------------------------------------

    def install_from_github(
        self,
        repo: str,
        app_name: str,
        executable_name: str,
        *,
        tag: str | None = None,
        preferred_patterns: Sequence[str] | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> InstallResult:
        """
        Download and install an application from a GitHub repository release.
        """
        arch = detect_system_arch()
        sys_os = detect_system_os()

        logger.info(
            "Installing '%s' from GitHub repo '%s' (detected arch=%s, os=%s)...",
            app_name,
            repo,
            arch.value,
            sys_os.value,
        )

        # 1. Fetch release payload
        if tag:
            release = self.github_client.get_release_by_tag(repo, tag)
        else:
            release = self.github_client.get_latest_release(repo)

        version = release.get("tag_name", "unknown")

        # 2. Select appropriate binary asset
        asset = self.github_client.select_asset(
            release=release,
            arch=arch,
            target_os=sys_os,
            preferred_patterns=preferred_patterns,
        )
        asset_name = asset["name"]
        download_url = asset["browser_download_url"]

        # 3. Discover checksum if available
        expected_sha = self.github_client.find_checksum(release, asset_name)
        if expected_sha:
            logger.info("Found expected SHA256 checksum for %s: %s", asset_name, expected_sha)
        else:
            logger.debug("No published checksum found for %s", asset_name)

        # 4. Download file
        cache_dir = self.settings.cache_dir / "downloads"
        cache_dir.mkdir(parents=True, exist_ok=True)
        archive_path = cache_dir / asset_name

        computed_sha = self.download_file(
            url=download_url,
            destination=archive_path,
            expected_sha256=expected_sha,
            progress_callback=progress_callback,
        )

        # 5. Extract and atomically activate (or copy a raw binary)
        install_root = self.settings.install_dir / app_name
        if _looks_like_archive(archive_path):
            executable_path = self.activate_archive(
                archive_path=archive_path,
                target_install_dir=install_root,
                executable_name=executable_name,
                app_name=app_name,
            )
        else:
            executable_path = self.activate_binary(
                binary_path=archive_path,
                target_install_dir=install_root,
                executable_name=executable_name,
                app_name=app_name,
            )

        # 6. Save installation metadata
        metadata = {
            "app_name": app_name,
            "version": version,
            "asset_name": asset_name,
            "sha256": computed_sha,
            "repo": repo,
            "installed_at": time.time(),
            "arch": arch.value,
        }
        metadata_file = install_root / ".amm_installed.json"
        with open(metadata_file, "w", encoding="utf-8") as fh:
            json.dump(metadata, fh, indent=2)

        # 7. Apply permissions
        self.storage_manager.apply_permissions(
            install_root,
            puid=self.settings.puid,
            pgid=self.settings.pgid,
            recursive=True,
        )

        logger.info(
            "Successfully installed '%s' %s to %s",
            app_name,
            version,
            executable_path,
        )

        return InstallResult(
            app_name=app_name,
            version=version,
            install_dir=install_root,
            executable_path=executable_path,
            asset_name=asset_name,
            sha256=computed_sha,
            installed_at=metadata["installed_at"],
        )

    def install_from_url(
        self,
        url: str,
        app_name: str,
        executable_name: str,
        version: str = "custom",
        expected_sha256: str | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> InstallResult:
        """
        Download and install an application from an arbitrary download URL.
        """
        filename = url.split("?")[0].rstrip("/").split("/")[-1]
        cache_dir = self.settings.cache_dir / "downloads"
        cache_dir.mkdir(parents=True, exist_ok=True)
        archive_path = cache_dir / filename

        computed_sha = self.download_file(
            url=url,
            destination=archive_path,
            expected_sha256=expected_sha256,
            progress_callback=progress_callback,
        )

        install_root = self.settings.install_dir / app_name
        executable_path = self.activate_archive(
            archive_path=archive_path,
            target_install_dir=install_root,
            executable_name=executable_name,
            app_name=app_name,
        )

        metadata = {
            "app_name": app_name,
            "version": version,
            "asset_name": filename,
            "sha256": computed_sha,
            "url": url,
            "installed_at": time.time(),
            "arch": detect_system_arch().value,
        }
        with open(install_root / ".amm_installed.json", "w", encoding="utf-8") as fh:
            json.dump(metadata, fh, indent=2)

        self.storage_manager.apply_permissions(
            install_root,
            puid=self.settings.puid,
            pgid=self.settings.pgid,
            recursive=True,
        )

        return InstallResult(
            app_name=app_name,
            version=version,
            install_dir=install_root,
            executable_path=executable_path,
            asset_name=filename,
            sha256=computed_sha,
            installed_at=metadata["installed_at"],
        )

    def install_from_pypi(
        self,
        package: str,
        app_name: str,
        *,
        extra_packages: Sequence[str] | None = None,
    ) -> InstallResult:
        """
        Create a dedicated virtualenv and install an official PyPI package.
        The executable is expected at ``{install_dir}/venv/bin/{package}``.
        """
        install_root = self.settings.install_dir / app_name
        venv_dir = install_root / "venv"
        install_root.mkdir(parents=True, exist_ok=True)

        logger.info("Creating virtualenv for '%s' at %s", app_name, venv_dir)
        subprocess.run(
            [sys.executable, "-m", "venv", str(venv_dir)],
            check=True,
            capture_output=True,
            text=True,
        )

        pip = venv_dir / "bin" / "pip"
        if not pip.is_file():
            pip = venv_dir / "Scripts" / "pip.exe"
        packages = [package, *(extra_packages or ())]
        logger.info("Installing PyPI packages for '%s': %s", app_name, ", ".join(packages))
        subprocess.run(
            [str(pip), "install", "--upgrade", "pip", *packages],
            check=True,
            capture_output=True,
            text=True,
        )

        executable = _find_venv_executable(venv_dir, package)
        if not executable:
            raise FileNotFoundError(
                f"PyPI package '{package}' installed but executable was not found in {venv_dir}."
            )

        version = "pypi"
        try:
            show = subprocess.run(
                [str(pip), "show", package],
                check=True,
                capture_output=True,
                text=True,
            )
            for line in show.stdout.splitlines():
                if line.lower().startswith("version:"):
                    version = line.split(":", 1)[1].strip()
                    break
        except subprocess.CalledProcessError:
            pass

        metadata = {
            "app_name": app_name,
            "version": version,
            "asset_name": package,
            "sha256": "",
            "source": "pypi",
            "installed_at": time.time(),
            "arch": detect_system_arch().value,
        }
        with open(install_root / ".amm_installed.json", "w", encoding="utf-8") as fh:
            json.dump(metadata, fh, indent=2)

        self.storage_manager.apply_permissions(
            install_root,
            puid=self.settings.puid,
            pgid=self.settings.pgid,
            recursive=True,
        )

        return InstallResult(
            app_name=app_name,
            version=version,
            install_dir=install_root,
            executable_path=executable,
            asset_name=package,
            sha256="",
            installed_at=metadata["installed_at"],
        )

    def install_from_github_source(
        self,
        repo: str,
        app_name: str,
        executable_name: str,
        *,
        tag: str | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> InstallResult:
        """Download a GitHub release zipball into the app install dir."""
        if tag:
            release = self.github_client.get_release_by_tag(repo, tag)
        else:
            release = self.github_client.get_latest_release(repo)
        version = release.get("tag_name", "unknown")
        zipball = release.get("zipball_url")
        if not zipball:
            raise ValueError(f"Release '{version}' for {repo} has no zipball_url")

        cache_dir = self.settings.cache_dir / "downloads"
        cache_dir.mkdir(parents=True, exist_ok=True)
        archive_path = cache_dir / f"{app_name}-{version}.zip"
        computed_sha = self.download_file(
            url=zipball,
            destination=archive_path,
            progress_callback=progress_callback,
        )
        install_root = self.settings.install_dir / app_name
        executable_path = self.activate_archive(
            archive_path=archive_path,
            target_install_dir=install_root,
            executable_name=executable_name,
            app_name=app_name,
        )
        metadata = {
            "app_name": app_name,
            "version": version,
            "asset_name": archive_path.name,
            "sha256": computed_sha,
            "repo": repo,
            "source": "github_zipball",
            "installed_at": time.time(),
            "arch": detect_system_arch().value,
        }
        with open(install_root / ".amm_installed.json", "w", encoding="utf-8") as fh:
            json.dump(metadata, fh, indent=2)
        self.storage_manager.apply_permissions(
            install_root,
            puid=self.settings.puid,
            pgid=self.settings.pgid,
            recursive=True,
        )
        return InstallResult(
            app_name=app_name,
            version=version,
            install_dir=install_root,
            executable_path=executable_path,
            asset_name=archive_path.name,
            sha256=computed_sha,
            installed_at=metadata["installed_at"],
        )

    # ------------------------------------------------------------------
    # Streaming Downloader
    # ------------------------------------------------------------------

    def download_file(
        self,
        url: str,
        destination: Path,
        expected_sha256: str | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
        chunk_size: int = 64 * 1024,
    ) -> str:
        """
        Stream a file to destination with SHA256 verification.
        Returns the computed SHA256 hex string.
        """
        destination = Path(destination).resolve()
        temp_dest = destination.with_name(f".{destination.name}.download-{uuid.uuid4().hex[:8]}")

        hasher = hashlib.sha256()
        logger.info("Downloading %s -> %s...", url, destination.name)

        try:
            with requests.get(url, stream=True, timeout=(15, 300)) as resp:
                resp.raise_for_status()
                total_size = int(resp.headers.get("content-length") or 0)
                downloaded = 0

                with open(temp_dest, "wb") as fh:
                    for chunk in resp.iter_content(chunk_size=chunk_size):
                        if not chunk:
                            continue
                        fh.write(chunk)
                        hasher.update(chunk)
                        downloaded += len(chunk)
                        if progress_callback and total_size > 0:
                            progress_callback(downloaded, total_size)

            computed_sha = hasher.hexdigest().lower()

            # Verify checksum if one was expected
            if expected_sha256:
                expected_clean = expected_sha256.strip().lower()
                if computed_sha != expected_clean:
                    raise ValueError(
                        f"Checksum verification failed for {destination.name}! "
                        f"Expected SHA256: {expected_clean}, Computed: {computed_sha}"
                    )
                logger.debug("SHA256 checksum verified successfully: %s", computed_sha)

            # Atomic swap of the downloaded archive
            os.replace(temp_dest, destination)
            return computed_sha

        except Exception:
            if temp_dest.exists():
                temp_dest.unlink(missing_ok=True)
            raise

    # ------------------------------------------------------------------
    # Transactional Activation
    # ------------------------------------------------------------------

    def activate_archive(
        self,
        archive_path: Path,
        target_install_dir: Path,
        executable_name: str,
        app_name: str,
    ) -> Path:
        """
        Extracts archive into an isolated staging folder, verifies the binary,
        and atomically swaps it into target_install_dir.
        """
        target_install_dir = Path(target_install_dir).resolve()
        parent_dir = target_install_dir.parent
        parent_dir.mkdir(parents=True, exist_ok=True)

        unique_id = uuid.uuid4().hex[:8]
        staging_dir = parent_dir / f".{app_name}.staging-{unique_id}"
        previous_backup_dir = parent_dir / f".{app_name}.previous-{unique_id}"

        try:
            # 1. Extract into isolated candidate staging folder
            ArchiveExtractor.extract(archive_path, staging_dir, strip_single_wrapper=True)

            # 2. Locate and verify executable inside staging
            exe_candidate = self._find_executable(staging_dir, executable_name)
            if not exe_candidate:
                raise FileNotFoundError(
                    f"Executable '{executable_name}' not found inside extracted archive for {app_name}."
                )

            # Ensure executable mode
            current_mode = exe_candidate.stat().st_mode
            exe_candidate.chmod(current_mode | 0o755)

            # 3. Atomic swap into place
            if target_install_dir.exists():
                os.replace(target_install_dir, previous_backup_dir)

            try:
                os.replace(staging_dir, target_install_dir)
            except Exception as swap_err:
                # Rollback if replace failed
                if previous_backup_dir.exists():
                    os.replace(previous_backup_dir, target_install_dir)
                raise swap_err

            # 4. Clean up previous backup
            if previous_backup_dir.exists():
                shutil.rmtree(previous_backup_dir, ignore_errors=True)

            # Return final path to executable inside target_install_dir
            final_exe = self._find_executable(target_install_dir, executable_name)
            if not final_exe:
                raise FileNotFoundError(
                    f"Executable '{executable_name}' missing after activation at {target_install_dir}"
                )
            return final_exe

        finally:
            if staging_dir.exists():
                shutil.rmtree(staging_dir, ignore_errors=True)
            if previous_backup_dir.exists():
                shutil.rmtree(previous_backup_dir, ignore_errors=True)

    def activate_binary(
        self,
        binary_path: Path,
        target_install_dir: Path,
        executable_name: str,
        app_name: str,
    ) -> Path:
        """Copy a standalone binary into the install directory."""
        target_install_dir = Path(target_install_dir).resolve()
        target_install_dir.mkdir(parents=True, exist_ok=True)
        dest = target_install_dir / executable_name
        shutil.copy2(binary_path, dest)
        dest.chmod(dest.stat().st_mode | 0o755)
        logger.info("Installed standalone binary for '%s' at %s", app_name, dest)
        return dest

    @staticmethod
    def _find_executable(base_dir: Path, name: str) -> Path | None:
        """
        Locate executable by name directly in base_dir or in immediate subdirectories.
        """
        direct = base_dir / name
        if direct.is_file():
            return direct

        for candidate in base_dir.rglob(name):
            if candidate.is_file():
                return candidate

        return None


def _find_venv_executable(venv_dir: Path, package: str) -> Path | None:
    names = [package, package.replace("-", "_")]
    if package.lower() == "sabnzbd":
        names = ["sabnzbdplus", "SABnzbd", "SABnzbd.py", package]
    if package.lower() == "bazarr":
        names = ["bazarr.py", package]
    seen: set[str] = set()
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        for candidate in (venv_dir / "bin" / name, venv_dir / "Scripts" / name, venv_dir / "Scripts" / f"{name}.exe"):
            if candidate.is_file():
                return candidate
    bin_dir = venv_dir / "bin"
    if bin_dir.is_dir():
        for child in bin_dir.iterdir():
            if child.is_file() and package.lower() in child.name.lower():
                return child
    return None


def _looks_like_archive(path: Path) -> bool:
    name = path.name.lower()
    return name.endswith(
        (".tar.gz", ".tgz", ".tar.xz", ".txz", ".tar.bz2", ".tbz2", ".tar", ".zip", ".deb", ".7z")
    )
