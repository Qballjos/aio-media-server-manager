"""
core/uninstall.py — Remove an application binary, optionally config/data.

Never deletes media libraries.
"""

from __future__ import annotations

import logging
import shutil
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
    await supervisor.stop(plugin.name)

    removed: list[str] = []
    if remove_application and plugin.install_dir.exists():
        shutil.rmtree(plugin.install_dir, ignore_errors=True)
        removed.append("application")
    if remove_config and plugin.config_dir.exists():
        shutil.rmtree(plugin.config_dir, ignore_errors=True)
        removed.append("configuration")
    if remove_data and plugin.data_dir.exists() and plugin.data_dir.resolve() != plugin.config_dir.resolve():
        shutil.rmtree(plugin.data_dir, ignore_errors=True)
        removed.append("data")

    logger.info("Uninstalled %s (removed=%s)", plugin.name, removed)
    return {
        "status": "uninstalled",
        "name": plugin.name,
        "removed": removed,
        "media_preserved": True,
    }


def _assert_not_media(path: Path, media_dir: Path, download_dir: Path) -> None:
    resolved = path.resolve()
    for forbidden in (media_dir, download_dir):
        if resolved == forbidden or resolved.is_relative_to(forbidden):
            raise UninstallError(
                f"Refusing to delete {resolved} because it is inside media/download storage."
            )
