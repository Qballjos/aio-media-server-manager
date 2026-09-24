"""
core/updater.py — Safe application updates with snapshot + rollback.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import time
from pathlib import Path
from typing import Any

import requests
from packaging.version import InvalidVersion, Version

from applications.base import BaseApplication
from applications.manifest import InstallMethod
from core.backup_manager import BackupManager
from core.installer.github import GitHubReleaseClient
from core.settings import Settings, settings
from core.supervisor import ProcessSupervisor

logger = logging.getLogger(__name__)


class ApplicationUpdater:
    def __init__(self, app_settings: Settings | None = None) -> None:
        self.settings = app_settings or settings
        self.backups = BackupManager(self.settings)
        self.github = GitHubReleaseClient(token=self.settings.github_token)

    def latest_version(self, plugin: BaseApplication) -> str | None:
        if plugin.manifest.install_method == InstallMethod.PYPI:
            return None
        if not plugin.manifest.github_repo:
            return None
        release = self.github.get_latest_release(plugin.manifest.github_repo)
        return str(release.get("tag_name") or release.get("name") or "").lstrip("v")

    def update_available(self, plugin: BaseApplication) -> dict[str, Any]:
        installed = (plugin.installed_metadata() or {}).get("version")
        latest = None
        try:
            latest = self.latest_version(plugin)
        except Exception as exc:
            logger.warning("Could not check updates for %s: %s", plugin.name, exc)
        return {
            "name": plugin.name,
            "installed_version": installed,
            "latest_version": latest,
            "update_available": _is_newer(latest, installed),
        }

    async def update(self, plugin: BaseApplication, *, start_after: bool = True) -> dict[str, Any]:
        if not plugin.is_installed():
            raise RuntimeError(f"{plugin.name} is not installed.")

        supervisor = ProcessSupervisor.get()
        was_running = supervisor.status(plugin.name).value == "running"
        if was_running:
            await supervisor.stop(plugin.name)

        snapshot = await asyncio.to_thread(self.backups.snapshot_application, plugin.name)
        previous_install = plugin.install_dir.with_name(f".{plugin.name}.pre-update")
        if previous_install.exists():
            shutil.rmtree(previous_install, ignore_errors=True)
        if plugin.install_dir.exists():
            shutil.copytree(plugin.install_dir, previous_install, dirs_exist_ok=True)

        try:
            result = plugin.install()
            healthy = True
            if start_after and plugin.manifest.daemon:
                await supervisor.start(
                    name=plugin.name,
                    cmd=plugin.start_command(),
                    cwd=plugin.working_directory(),
                    env=plugin.extra_env(),
                    log_dir=self.settings.config_dir / "logs",
                )
                healthy = self._wait_healthy(plugin)
                if not healthy:
                    raise RuntimeError("Post-update health check failed.")
            return {
                "status": "updated",
                "name": plugin.name,
                "version": result.version,
                "snapshot": str(snapshot),
                "healthy": healthy,
            }
        except Exception as exc:
            logger.error("Update failed for %s: %s — rolling back", plugin.name, exc)
            await supervisor.stop(plugin.name)
            if previous_install.exists():
                if plugin.install_dir.exists():
                    shutil.rmtree(plugin.install_dir, ignore_errors=True)
                shutil.move(str(previous_install), str(plugin.install_dir))
            try:
                self.backups.restore_application_snapshot(snapshot)
            except Exception as restore_exc:
                logger.error("Snapshot restore also failed for %s: %s", plugin.name, restore_exc)
            if was_running and plugin.manifest.daemon:
                try:
                    await supervisor.start(
                        name=plugin.name,
                        cmd=plugin.start_command(),
                        cwd=plugin.working_directory(),
                        env=plugin.extra_env(),
                        log_dir=self.settings.config_dir / "logs",
                    )
                except Exception:
                    logger.exception("Failed to restart previous version of %s", plugin.name)
            return {
                "status": "rolled_back",
                "name": plugin.name,
                "error": str(exc),
                "snapshot": str(snapshot),
            }
        finally:
            if previous_install.exists():
                shutil.rmtree(previous_install, ignore_errors=True)

    def _wait_healthy(self, plugin: BaseApplication, timeout: float = 45.0) -> bool:
        url = plugin.health_check_url()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                resp = requests.get(url, timeout=3)
                if resp.status_code < 500:
                    return True
            except requests.RequestException:
                time.sleep(1.5)
                continue
            time.sleep(1.5)
        return False


def _is_newer(latest: str | None, installed: str | None) -> bool:
    if not latest or not installed:
        return bool(latest and latest != installed)
    try:
        return Version(_strip_v(latest)) > Version(_strip_v(installed))
    except InvalidVersion:
        return latest.lstrip("v") != installed.lstrip("v")


def _strip_v(value: str) -> str:
    value = value.strip()
    if value.lower().startswith("v") and value[1:2].isdigit():
        return value[1:]
    return value
