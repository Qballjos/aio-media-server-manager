"""
core/uninstall.py — Remove an application binary, optionally config/data.

Never deletes media libraries.
"""

from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path
from typing import Any

from applications.base import BaseApplication
from core.settings import Settings, settings
from core.supervisor import ProcessSupervisor

logger = logging.getLogger(__name__)


class UninstallError(ValueError):
    pass


async def uninstall_application(
    plugin: BaseApplication,
    *,
    remove_application: bool = True,
    remove_config: bool = False,
    remove_data: bool = False,
    app_settings: Settings | None = None,
) -> dict[str, Any]:
    cfg = app_settings or settings
    media_dir = Path(cfg.media_dir).resolve()
    download_dir = Path(cfg.download_dir).resolve()

    for target in (plugin.config_dir, plugin.data_dir, plugin.install_dir):
        _assert_not_media(target, media_dir, download_dir)

    supervisor = ProcessSupervisor.get()
    try:
        await supervisor.stop(plugin.name, timeout=8.0)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Stop before uninstall of %s failed: %s", plugin.name, exc)
    supervisor.forget(plugin.name)

    removed: list[str] = []
    leftover: list[str] = []
    if remove_application and plugin.install_dir.exists():
        if _remove_tree(plugin.install_dir):
            removed.append("application")
        else:
            leftover.append(str(plugin.install_dir))
    if remove_config and plugin.config_dir.exists():
        if _remove_tree(plugin.config_dir):
            removed.append("configuration")
        else:
            leftover.append(str(plugin.config_dir))
    if (
        remove_data
        and plugin.data_dir.exists()
        and plugin.data_dir.resolve() != plugin.config_dir.resolve()
    ):
        if _remove_tree(plugin.data_dir):
            removed.append("data")
        else:
            leftover.append(str(plugin.data_dir))

    if leftover:
        raise UninstallError(
            f"Could not fully remove {plugin.name}; leftover paths: {', '.join(leftover)}"
        )

    logger.info("Uninstalled %s (removed=%s)", plugin.name, removed)
    return {
        "status": "uninstalled",
        "name": plugin.name,
        "removed": removed,
        "media_preserved": True,
    }


def _remove_tree(path: Path) -> bool:
    if not path.exists():
        return True
    try:
        shutil.rmtree(path)
    except OSError as exc:
        logger.warning("rmtree %s failed (%s); retrying", path, exc)
        time.sleep(0.25)
        shutil.rmtree(path, ignore_errors=True)
    return not path.exists()


def _assert_not_media(path: Path, media_dir: Path, download_dir: Path) -> None:
    resolved = path.resolve()
    for forbidden in (media_dir, download_dir):
        if resolved == forbidden or resolved.is_relative_to(forbidden):
            raise UninstallError(
                f"Refusing to delete {resolved} because it is inside media/download storage."
            )
