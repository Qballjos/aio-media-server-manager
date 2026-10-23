"""
core/updater.py — Safe application updates with snapshot + rollback.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import requests
from packaging.version import InvalidVersion, Version

from applications.base import BaseApplication
from applications.manifest import InstallMethod
from core.backup_manager import BackupManager
from core.install_jobs import set_job
from core.installer.github import GitHubReleaseClient
from core.settings import Settings, settings
from core.supervisor import ProcessSupervisor
from core.vpn import VpnIsolationError

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
        """
        Install the latest version with a rollback on failure. Each step is reported as the app's job, so Catalog,
        Settings and Home can show where it is; the slow parts run in threads, so the API keeps answering.
        """
        if not plugin.is_installed():
            raise RuntimeError(f"{plugin.name} is not installed.")

        label = plugin.manifest.display_name

        def step(message: str) -> None:
            set_job(plugin.name, "updating", message)

        supervisor = ProcessSupervisor.get()
        was_running = supervisor.status(plugin.name).value == "running"
        if was_running:
            step(f"Stopping {label}…")
            await supervisor.stop(plugin.name)

        previous_install = plugin.install_dir.with_name(f".{plugin.name}.pre-update")
        try:
            step(f"Backing up {label}'s settings…")
            snapshot = await asyncio.to_thread(self.backups.snapshot_application, plugin.name)
            step("Setting the current version aside…")
            await asyncio.to_thread(_set_aside, plugin.install_dir, previous_install)
        except Exception as exc:
            set_job(plugin.name, "rolled_back", f"The update did not start: {exc}")
            raise

        try:
            plugin.require_host_arch()
            step(f"Installing the new version of {label}…")
            result = await asyncio.to_thread(plugin.install)
            healthy = True
            if start_after and plugin.manifest.daemon:
                step(f"Starting {label}…")
                try:
                    await supervisor.start(
                        name=plugin.name,
                        cmd=plugin.start_command(),
                        cwd=plugin.working_directory(),
                        env=plugin.extra_env(),
                        log_dir=self.settings.config_dir / "logs",
                    )
                except VpnIsolationError as exc:
                    logger.warning("Updated '%s' but left it stopped: %s", plugin.name, exc)
                    set_job(plugin.name, "updated", f"Updated to {result.version}, but stopped: {exc}")
                    return {
                        "status": "updated",
                        "name": plugin.name,
                        "version": result.version,
                        "snapshot": str(snapshot),
                        "healthy": False,
                        "start_error": str(exc),
                    }
                step(f"Waiting for {label} to answer…")
                healthy = await asyncio.to_thread(self._wait_healthy, plugin)
                if not healthy:
                    raise RuntimeError("Post-update health check failed.")
            set_job(plugin.name, "updated", f"Updated to {result.version}")
            return {
                "status": "updated",
                "name": plugin.name,
                "version": result.version,
                "snapshot": str(snapshot),
                "healthy": healthy,
            }
        except Exception as exc:
            logger.error("Update failed for %s: %s — rolling back", plugin.name, exc)
            step(f"Update failed; putting the previous version of {label} back…")
            await supervisor.stop(plugin.name)
            if previous_install.exists():
                if plugin.install_dir.exists():
                    await asyncio.to_thread(shutil.rmtree, plugin.install_dir, ignore_errors=True)
                await asyncio.to_thread(shutil.move, str(previous_install), str(plugin.install_dir))
            try:
                await asyncio.to_thread(self.backups.restore_application_snapshot, snapshot)
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
            set_job(plugin.name, "rolled_back", f"Update failed, back on the previous version: {exc}")
            return {
                "status": "rolled_back",
                "name": plugin.name,
                "error": str(exc),
                "snapshot": str(snapshot),
            }
        finally:
            if previous_install.exists():
                _discard_later(previous_install)

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


def _set_aside(install_dir: Path, previous: Path) -> None:
    """
    Move the installed version out of the way for a rollback. App folders hold program files only (backups skip
    them), so a rename does what copying every file did, in no time. Leftovers of earlier updates go first: at most
    one old version per app.
    """
    for leftover in install_dir.parent.glob(f"{previous.name}*"):
        shutil.rmtree(leftover, ignore_errors=True)
    if install_dir.exists():
        try:
            install_dir.rename(previous)
        except OSError:
            # ponytail: a folder that cannot be renamed (a mount point) is copied, as before
            shutil.copytree(install_dir, previous, dirs_exist_ok=True)
    install_dir.mkdir(parents=True, exist_ok=True)


def _discard_later(path: Path) -> None:
    """Delete an old version in the background so the update can answer; the next update clears what a restart left."""
    trash = path.with_name(f"{path.name}-{uuid.uuid4().hex[:8]}")
    try:
        path.rename(trash)
    except OSError:
        trash = path
    threading.Thread(target=shutil.rmtree, args=(trash,), kwargs={"ignore_errors": True}, daemon=True).start()


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
