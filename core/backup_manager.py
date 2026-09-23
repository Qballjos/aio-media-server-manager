"""
core/backup_manager.py — Configuration backup and restore.

Backs up manager config, application config, secrets, and databases.
Never includes media libraries, torrent payloads, temp files, or caches.
"""

from __future__ import annotations

import json
import logging
import shutil
import tarfile
import tempfile
import time
from pathlib import Path
from typing import Any, Iterable

from core.settings import Settings, settings

logger = logging.getLogger(__name__)

_SKIP_DIR_NAMES = {
    "cache",
    "downloads",
    "apps",
    "logs",
    "tmp",
    "temp",
    "__pycache__",
}
_SKIP_SUFFIXES = {".mkv", ".mp4", ".avi", ".iso", ".nzb", ".torrent", ".part"}


class BackupManager:
    def __init__(self, app_settings: Settings | None = None) -> None:
        self.settings = app_settings or settings

    @property
    def backup_root(self) -> Path:
        return Path(self.settings.backup_dir)

    def create_backup(self, label: str | None = None) -> dict[str, Any]:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        name = f"amm-{stamp}"
        if label:
            safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in label)[:40]
            name = f"{name}-{safe}"
        archive_path = self.backup_root / f"{name}.tar.gz"
        self.backup_root.mkdir(parents=True, exist_ok=True)

        manifest = {
            "created_at": time.time(),
            "label": label,
            "config_dir": str(self.settings.config_dir),
            "includes": ["amm_config.json", "application config", "secrets", "databases"],
            "excludes": ["media", "downloads", "caches", "install binaries"],
        }

        with tarfile.open(archive_path, "w:gz") as tar:
            config_dir = Path(self.settings.config_dir)
            if config_dir.is_dir():
                for path in config_dir.rglob("*"):
                    if not path.is_file():
                        continue
                    if self._should_skip(path, config_dir):
                        continue
                    tar.add(path, arcname=str(path.relative_to(config_dir)))
            buf = tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False)
            try:
                json.dump(manifest, buf, indent=2)
                buf.close()
                tar.add(buf.name, arcname=".amm_backup.json")
            finally:
                Path(buf.name).unlink(missing_ok=True)

        self.prune()
        logger.info("Created configuration backup %s", archive_path)
        return {
            "name": archive_path.name,
            "path": str(archive_path),
            "size_bytes": archive_path.stat().st_size,
            "created_at": manifest["created_at"],
        }

    def list_backups(self) -> list[dict[str, Any]]:
        if not self.backup_root.is_dir():
            return []
        items = []
        for path in sorted(self.backup_root.glob("amm-*.tar.gz"), reverse=True):
            items.append(
                {
                    "name": path.name,
                    "path": str(path),
                    "size_bytes": path.stat().st_size,
                    "modified_at": path.stat().st_mtime,
                }
            )
        return items

    def restore_backup(self, name: str) -> dict[str, Any]:
        archive = self.backup_root / name
        if not archive.is_file():
            raise FileNotFoundError(f"Backup not found: {name}")
        dest = Path(self.settings.config_dir)
        dest.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive, "r:gz") as tar:
            _safe_extract(tar, dest)
        logger.info("Restored configuration backup %s into %s", name, dest)
        return {"status": "restored", "name": name, "destination": str(dest)}

    def prune(self, keep: int | None = None) -> list[str]:
        keep = keep if keep is not None else self.settings.backup_retention
        removed: list[str] = []
        backups = sorted(self.backup_root.glob("amm-*.tar.gz"), key=lambda p: p.stat().st_mtime)
        while len(backups) > keep:
            victim = backups.pop(0)
            victim.unlink(missing_ok=True)
            removed.append(victim.name)
        return removed

    def snapshot_application(self, app_name: str, paths: Iterable[Path]) -> Path:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        dest_dir = self.backup_root / app_name
        dest_dir.mkdir(parents=True, exist_ok=True)
        archive = dest_dir / f"{app_name}-{stamp}.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            for path in paths:
                path = Path(path)
                if path.exists():
                    tar.add(path, arcname=path.name)
        return archive

    def restore_application_snapshot(self, archive: Path, destination: Path) -> None:
        destination.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive, "r:gz") as tar:
            _safe_extract(tar, destination)

    def _should_skip(self, path: Path, config_root: Path) -> bool:
        try:
            rel = path.relative_to(config_root)
        except ValueError:
            return True
        if any(part in _SKIP_DIR_NAMES for part in rel.parts):
            return True
        if path.suffix.lower() in _SKIP_SUFFIXES:
            return True
        if path.stat().st_size > 100 * 1024 * 1024:
            return True
        media_dir = Path(self.settings.media_dir).resolve()
        download_dir = Path(self.settings.download_dir).resolve()
        resolved = path.resolve()
        if resolved == media_dir or resolved.is_relative_to(media_dir):
            return True
        if resolved == download_dir or resolved.is_relative_to(download_dir):
            return True
        return False


def _safe_extract(tar: tarfile.TarFile, dest: Path) -> None:
    if hasattr(tarfile, "data_filter"):
        tar.extractall(dest, filter="data")
    else:
        tar.extractall(dest)
