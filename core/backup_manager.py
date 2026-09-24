"""
core/backup_manager.py — Configuration backup and restore.

Archives the manager config, per-app config, secrets and databases from
``config_dir``. SQLite databases are copied with SQLite's online backup API so
they stay consistent while apps run. Media, downloads, install binaries,
caches, logs, artwork caches and the backup folder itself are never included.

Archive layout (format 2): members are paths relative to ``config_dir`` plus a
``.amm_backup.json`` manifest (sections, per-file SHA-256, warnings). A
``<archive>.json`` sidecar next to each archive keeps listing cheap.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import re
import shutil
import sqlite3
import tarfile
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Optional

from core.settings import Settings, settings

logger = logging.getLogger(__name__)

FORMAT_VERSION = 2
MANIFEST_NAME = ".amm_backup.json"
MANAGER_SECTION = "manager"
SNAPSHOT_DIR_NAME = "app-snapshots"
SNAPSHOT_KEEP = 3

_NAME_RE = re.compile(r"^amm-[A-Za-z0-9_-]+\.tar\.gz$")
_SQLITE_MAGIC = b"SQLite format 3\x00"
_SQLITE_SIDECARS = ("-wal", "-shm", "-journal")
_SPOOL_BYTES = 32 * 1024 * 1024
_CHUNK = 1024 * 1024

# Top-level entries of config_dir that never belong in a config backup.
_SKIP_TOP_LEVEL = {"backups", "apps", "cache", "logs", "tmp"}
# Directory names skipped at any depth (compared lower-case).
_SKIP_DIR_NAMES = {
    "__pycache__",
    "backups",
    "cache",
    "caches",
    "crash reports",
    "diagnostics",
    "log",
    "logs",
    "temp",
    "tmp",
    "transcode",
    "transcodes",
}
# Rebuildable artwork / extraction caches, keyed by the app's top-level folder.
_APP_SKIP_DIR_NAMES = {
    "jellyfin": {"metadata", "keyframes", "attachments", "subtitles"},
    "plex": {"media", "metadata", "codecs", "updates"},
}
_SKIP_FILE_NAMES = {"logs.db"}
_SKIP_SUFFIXES = {".mkv", ".mp4", ".avi", ".m4v", ".iso", ".nzb", ".part", ".pid", ".lock", ".tmp"}

ProgressFn = Callable[[int, int], None]


class BackupError(RuntimeError):
    pass


class BackupManager:
    def __init__(self, app_settings: Settings | None = None) -> None:
        self.settings = app_settings or settings

    # ------------------------------------------------------------------
    # Locations
    # ------------------------------------------------------------------

    @property
    def backup_root(self) -> Path:
        return Path(self.settings.backup_dir)

    @property
    def config_root(self) -> Path:
        return Path(self.settings.config_dir)

    @property
    def legacy_root(self) -> Path:
        return self.config_root / "backups"

    @property
    def snapshot_root(self) -> Path:
        return self.backup_root / SNAPSHOT_DIR_NAME

    def _roots(self) -> list[tuple[str, Path]]:
        roots = [("primary", self.backup_root)]
        if self.legacy_root.resolve() != self.backup_root.resolve():
            roots.append(("legacy", self.legacy_root))
        return roots

    def resolve_archive(self, name: str) -> Path:
        if not _NAME_RE.match(name or ""):
            raise FileNotFoundError(f"Backup not found: {name}")
        for _label, root in self._roots():
            candidate = root / name
            if candidate.is_file() and candidate.parent.resolve() == root.resolve():
                return candidate
        raise FileNotFoundError(f"Backup not found: {name}")

    # ------------------------------------------------------------------
    # Sections and file selection
    # ------------------------------------------------------------------

    def app_sections(self) -> dict[str, str]:
        """Map top-level config folder → app name."""
        from applications.catalog import ApplicationCatalog

        mapping: dict[str, str] = {}
        try:
            for plugin in ApplicationCatalog(app_settings=self.settings).all_plugins():
                top = Path(plugin.manifest.config_subdir or plugin.name).parts[0]
                mapping.setdefault(top, plugin.name)
        except Exception as exc:
            logger.debug("Could not load catalog for backup sections: %s", exc)
        return mapping

    def section_for(self, rel: str, mapping: dict[str, str]) -> str:
        parts = Path(rel).parts
        if len(parts) > 1 and parts[0] in mapping:
            return mapping[parts[0]]
        return MANAGER_SECTION

    def _excluded_top_paths(self) -> set[str]:
        excluded = set(_SKIP_TOP_LEVEL)
        root = self.config_root.resolve()
        for path in (self.settings.install_dir, self.settings.cache_dir, self.settings.backup_dir):
            if not path:
                continue
            try:
                excluded.add(Path(path).resolve().relative_to(root).as_posix())
            except ValueError:
                continue
        return excluded

    def is_excluded(self, rel: str, *, is_dir: bool = False, excluded_top: set[str] | None = None) -> bool:
        path = Path(rel)
        parts = path.parts
        if not parts:
            return False
        excluded_top = excluded_top if excluded_top is not None else self._excluded_top_paths()
        posix = path.as_posix()
        for top in excluded_top:
            if posix == top or posix.startswith(top + "/"):
                return True
        app_skip = _APP_SKIP_DIR_NAMES.get(parts[0].lower(), set())
        dir_parts = parts if is_dir else parts[:-1]
        for part in dir_parts[1:]:
            lowered = part.lower()
            if lowered in _SKIP_DIR_NAMES or lowered in app_skip:
                return True
        if is_dir:
            return False
        name = parts[-1].lower()
        if name == MANIFEST_NAME or name in _SKIP_FILE_NAMES:
            return True
        if any(name.endswith(suffix) for suffix in _SQLITE_SIDECARS):
            return True
        return Path(name).suffix in _SKIP_SUFFIXES

    def iter_files(self, sections: Optional[Iterable[str]] = None) -> Iterator[tuple[Path, str, str]]:
        """Yield (absolute path, archive name, section) for every file to back up."""
        root = self.config_root
        if not root.is_dir():
            return
        wanted = _normalise_sections(sections)
        mapping = self.app_sections()
        excluded_top = self._excluded_top_paths()
        media = Path(self.settings.media_dir).resolve()
        downloads = Path(self.settings.download_dir).resolve()
        for dirpath, dirnames, filenames in os.walk(root):
            current = Path(dirpath)
            rel_dir = current.relative_to(root)
            keep_dirs = []
            for dirname in sorted(dirnames):
                rel = (rel_dir / dirname).as_posix()
                full = current / dirname
                if full.is_symlink() or self.is_excluded(rel, is_dir=True, excluded_top=excluded_top):
                    continue
                if wanted is not None and rel_dir == Path(".") and mapping.get(dirname, MANAGER_SECTION) not in wanted:
                    continue
                resolved = full.resolve()
                if resolved == media or resolved.is_relative_to(media):
                    continue
                if resolved == downloads or resolved.is_relative_to(downloads):
                    continue
                keep_dirs.append(dirname)
            dirnames[:] = keep_dirs
            for filename in sorted(filenames):
                full = current / filename
                rel = (rel_dir / filename).as_posix()
                if full.is_symlink() or self.is_excluded(rel, excluded_top=excluded_top):
                    continue
                section = self.section_for(rel, mapping)
                if wanted is not None and section not in wanted:
                    continue
                yield full, rel, section

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create_backup(
        self,
        label: str | None = None,
        *,
        kind: str = "manual",
        sections: Optional[Iterable[str]] = None,
        progress: ProgressFn | None = None,
        prune: bool = True,
    ) -> dict[str, Any]:
        self.backup_root.mkdir(parents=True, exist_ok=True)
        archive_path = self._unique_archive_path(label or kind)
        manifest = self._write_archive(archive_path, sections=sections, kind=kind, label=label, progress=progress)
        _write_sidecar(archive_path, manifest)
        if prune:
            self.prune()
        logger.info(
            "Created %s backup %s (%d files, %d warnings)",
            kind,
            archive_path,
            len(manifest["files"]),
            len(manifest["warnings"]),
        )
        return self._describe(archive_path, manifest, "primary")

    def _unique_archive_path(self, label: str) -> Path:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in label)[:40].strip("-") or "backup"
        candidate = self.backup_root / f"amm-{stamp}-{safe}.tar.gz"
        counter = 2
        while candidate.exists():
            candidate = self.backup_root / f"amm-{stamp}-{safe}-{counter}.tar.gz"
            counter += 1
        return candidate

    def _write_archive(
        self,
        archive_path: Path,
        *,
        sections: Optional[Iterable[str]],
        kind: str,
        label: str | None,
        progress: ProgressFn | None,
    ) -> dict[str, Any]:
        files = list(self.iter_files(sections))
        manifest: dict[str, Any] = {
            "format": FORMAT_VERSION,
            "created_at": time.time(),
            "kind": kind,
            "label": label,
            "amm_version": _amm_version(),
            "config_dir": str(self.config_root),
            "sections": [],
            "files": {},
            "warnings": [],
        }
        seen_sections: set[str] = set()
        partial = archive_path.with_name(archive_path.name + ".partial")
        staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=archive_path.parent))
        try:
            with tarfile.open(partial, "w:gz", compresslevel=6) as tar:
                total = len(files)
                for index, (path, rel, section) in enumerate(files, start=1):
                    try:
                        entry = _add_file(tar, path, rel, staging, manifest["warnings"])
                    except OSError as exc:
                        manifest["warnings"].append(f"{rel}: could not read ({exc})")
                    else:
                        manifest["files"][rel] = entry
                        seen_sections.add(section)
                    if progress:
                        progress(index, total)
                manifest["sections"] = sorted(seen_sections)
                payload = json.dumps(manifest, indent=2).encode("utf-8")
                info = tarfile.TarInfo(MANIFEST_NAME)
                info.size = len(payload)
                info.mtime = int(time.time())
                info.mode = 0o600
                tar.addfile(info, io.BytesIO(payload))
            os.replace(partial, archive_path)
        finally:
            partial.unlink(missing_ok=True)
            shutil.rmtree(staging, ignore_errors=True)
        return manifest

    # ------------------------------------------------------------------
    # List / inspect / verify
    # ------------------------------------------------------------------

    def list_backups(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for location, root in self._roots():
            if not root.is_dir():
                continue
            for path in root.glob("amm-*.tar.gz"):
                if not _NAME_RE.match(path.name):
                    continue
                items.append(self._describe(path, _read_sidecar(path), location))
        items.sort(key=lambda item: item.get("created_at") or 0, reverse=True)
        return items

    def _describe(self, path: Path, manifest: dict[str, Any] | None, location: str) -> dict[str, Any]:
        stat = path.stat()
        manifest = manifest or {}
        return {
            "name": path.name,
            "path": str(path),
            "location": location,
            "size_bytes": stat.st_size,
            "created_at": manifest.get("created_at") or stat.st_mtime,
            "modified_at": stat.st_mtime,
            "format": int(manifest.get("format") or 1),
            "kind": manifest.get("kind") or "manual",
            "label": manifest.get("label"),
            "sections": manifest.get("sections") or [],
            "file_count": len(manifest.get("files") or {}) or None,
            "warnings": manifest.get("warnings") or [],
            "amm_version": manifest.get("amm_version") or "",
        }

    def read_manifest(self, archive: Path) -> dict[str, Any]:
        with tarfile.open(archive, "r:gz") as tar:
            for member in tar:
                if member.name == MANIFEST_NAME and member.isfile():
                    handle = tar.extractfile(member)
                    if handle is None:
                        break
                    try:
                        data = json.loads(handle.read().decode("utf-8"))
                    except (ValueError, UnicodeDecodeError):
                        return {}
                    return data if isinstance(data, dict) else {}
        return {}

    def ensure_sidecar(self, archive: Path) -> dict[str, Any]:
        manifest = self.read_manifest(archive)
        if not manifest:
            manifest = {"format": 1, "created_at": archive.stat().st_mtime, "kind": "uploaded"}
        _write_sidecar(archive, manifest)
        return manifest

    def verify_backup(self, name: str, progress: ProgressFn | None = None) -> dict[str, Any]:
        archive = self.resolve_archive(name)
        manifest = _read_sidecar(archive) or self.read_manifest(archive)
        expected: dict[str, dict[str, Any]] = manifest.get("files") or {}
        mismatched: list[str] = []
        checked = 0
        present: set[str] = set()
        try:
            with tarfile.open(archive, "r:gz") as tar:
                total = len(expected) or 0
                for member in tar:
                    if not member.isfile() or member.name == MANIFEST_NAME:
                        continue
                    handle = tar.extractfile(member)
                    digest = hashlib.sha256()
                    if handle is not None:
                        for chunk in iter(lambda: handle.read(_CHUNK), b""):
                            digest.update(chunk)
                    checked += 1
                    present.add(member.name)
                    want = expected.get(member.name)
                    if want and want.get("sha256") != digest.hexdigest():
                        mismatched.append(member.name)
                    if progress:
                        progress(checked, max(total, checked))
        except (tarfile.TarError, OSError, EOFError) as exc:
            return {"name": name, "ok": False, "checked": checked, "error": f"archive is damaged: {exc}"}
        missing = sorted(set(expected) - present)
        ok = not mismatched and not missing
        return {
            "name": name,
            "ok": ok,
            "format": int(manifest.get("format") or 1),
            "checked": checked,
            "mismatched": mismatched,
            "missing": missing,
            "error": "" if ok else "checksum mismatch or missing files",
        }

    # ------------------------------------------------------------------
    # Restore
    # ------------------------------------------------------------------

    def restore_backup(
        self,
        name: str,
        sections: Optional[Iterable[str]] = None,
        progress: ProgressFn | None = None,
    ) -> dict[str, Any]:
        """Write archive files back into config_dir. Callers stop affected apps first."""
        archive = self.resolve_archive(name)
        restored = self._extract(archive, _normalise_sections(sections), progress)
        logger.info("Restored backup %s into %s (%s)", name, self.config_root, ", ".join(restored["sections"]))
        return {"status": "restored", "name": name, "destination": str(self.config_root), **restored}

    def backup_sections(self, name: str) -> list[str]:
        archive = self.resolve_archive(name)
        manifest = _read_sidecar(archive)
        if manifest.get("sections"):
            return list(manifest["sections"])
        mapping = self.app_sections()
        found: set[str] = set()
        with tarfile.open(archive, "r:gz") as tar:
            for member in tar:
                if member.isfile() and member.name != MANIFEST_NAME:
                    found.add(self.section_for(member.name, mapping))
        return sorted(found)

    def _extract(
        self,
        archive: Path,
        wanted: Optional[set[str]],
        progress: ProgressFn | None,
    ) -> dict[str, Any]:
        dest = self.config_root
        dest.mkdir(parents=True, exist_ok=True)
        mapping = self.app_sections()
        excluded_top = self._excluded_top_paths()
        restored_sections: set[str] = set()
        count = 0
        with tarfile.open(archive, "r:gz") as tar:
            members = []
            for member in tar.getmembers():
                if member.name == MANIFEST_NAME or not (member.isfile() or member.isdir()):
                    continue
                rel = member.name[2:] if member.name.startswith("./") else member.name
                if not rel or rel == "." or self.is_excluded(rel, is_dir=member.isdir(), excluded_top=excluded_top):
                    continue
                section = self.section_for(rel, mapping)
                if wanted is not None and section not in wanted:
                    continue
                members.append((member, section))
            total = len(members)
            for index, (member, section) in enumerate(members, start=1):
                target = dest / member.name
                if member.isfile():
                    for suffix in _SQLITE_SIDECARS:
                        Path(f"{target}{suffix}").unlink(missing_ok=True)
                _extract_member(tar, member, dest)
                if member.isfile():
                    count += 1
                    restored_sections.add(section)
                    self._chown(target)
                if progress:
                    progress(index, total)
        return {"sections": sorted(restored_sections), "files": count}

    def _chown(self, path: Path) -> None:
        if not hasattr(os, "geteuid") or os.geteuid() != 0:
            return
        uid, gid = int(self.settings.puid), int(self.settings.pgid)
        root = self.config_root
        try:
            os.chown(path, uid, gid, follow_symlinks=False)
            for parent in path.parents:
                if parent == root or root not in parent.parents:
                    break
                os.chown(parent, uid, gid, follow_symlinks=False)
        except OSError as exc:
            logger.debug("chown %s failed: %s", path, exc)

    # ------------------------------------------------------------------
    # Retention
    # ------------------------------------------------------------------

    def prune(self, keep: int | None = None) -> list[str]:
        keep = max(1, keep if keep is not None else self.settings.backup_retention)
        if not self.backup_root.is_dir():
            return []
        backups = sorted(
            (p for p in self.backup_root.glob("amm-*.tar.gz") if _NAME_RE.match(p.name)),
            key=lambda p: p.stat().st_mtime,
        )
        removed: list[str] = []
        while len(backups) > keep:
            victim = backups.pop(0)
            self.delete_archive(victim)
            removed.append(victim.name)
        return removed

    def delete_backup(self, name: str) -> None:
        self.delete_archive(self.resolve_archive(name))

    @staticmethod
    def delete_archive(archive: Path) -> None:
        archive.unlink(missing_ok=True)
        _sidecar_path(archive).unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # Per-app snapshots used by the updater
    # ------------------------------------------------------------------

    def snapshot_application(self, app_name: str) -> Path:
        dest_dir = self.snapshot_root / app_name
        dest_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        archive = dest_dir / f"{app_name}-{stamp}.tar.gz"
        counter = 2
        while archive.exists():
            archive = dest_dir / f"{app_name}-{stamp}-{counter}.tar.gz"
            counter += 1
        self._write_archive(archive, sections=[app_name], kind="pre-update", label=app_name, progress=None)
        snapshots = sorted(dest_dir.glob(f"{app_name}-*.tar.gz"), key=lambda p: p.stat().st_mtime)
        for victim in snapshots[:-SNAPSHOT_KEEP]:
            victim.unlink(missing_ok=True)
        return archive

    def restore_application_snapshot(self, archive: Path) -> dict[str, Any]:
        return self._extract(Path(archive), None, None)


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _normalise_sections(sections: Optional[Iterable[str]]) -> Optional[set[str]]:
    if sections is None:
        return None
    wanted = {str(item).strip().lower() for item in sections if str(item).strip()}
    if not wanted or "all" in wanted:
        return None
    return wanted


def _is_sqlite(path: Path) -> bool:
    try:
        with path.open("rb") as fh:
            return fh.read(16) == _SQLITE_MAGIC
    except OSError:
        return False


def _sqlite_snapshot(src: Path, dst: Path) -> None:
    source = sqlite3.connect(f"{src.resolve().as_uri()}?mode=ro", uri=True, timeout=30)
    try:
        target = sqlite3.connect(str(dst))
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()


def _add_file(tar: tarfile.TarFile, path: Path, rel: str, staging: Path, warnings: list[str]) -> dict[str, Any]:
    info = tar.gettarinfo(str(path), arcname=rel)
    source = path
    snapshot: Path | None = None
    method = "copy"
    if _is_sqlite(path):
        snapshot = staging / f"db-{os.getpid()}-{time.monotonic_ns()}.sqlite"
        try:
            _sqlite_snapshot(path, snapshot)
            source = snapshot
            method = "sqlite"
        except sqlite3.Error as exc:
            warnings.append(f"{rel}: copied without SQLite snapshot ({exc})")
            snapshot.unlink(missing_ok=True)
            snapshot = None
    digest = hashlib.sha256()
    size = 0
    try:
        with tempfile.SpooledTemporaryFile(max_size=_SPOOL_BYTES, dir=staging) as spool:
            with source.open("rb") as fh:
                for chunk in iter(lambda: fh.read(_CHUNK), b""):
                    digest.update(chunk)
                    spool.write(chunk)
                    size += len(chunk)
            spool.seek(0)
            info.size = size
            tar.addfile(info, spool)
    finally:
        if snapshot is not None:
            snapshot.unlink(missing_ok=True)
    return {"size": size, "sha256": digest.hexdigest(), "method": method}


def _extract_member(tar: tarfile.TarFile, member: tarfile.TarInfo, dest: Path) -> None:
    if hasattr(tarfile, "data_filter"):
        tar.extract(member, dest, filter="data")
    else:
        tar.extract(member, dest)


def _sidecar_path(archive: Path) -> Path:
    return archive.with_name(archive.name + ".json")


def _write_sidecar(archive: Path, manifest: dict[str, Any]) -> None:
    try:
        _sidecar_path(archive).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    except OSError as exc:
        logger.debug("Could not write backup sidecar for %s: %s", archive, exc)


def _read_sidecar(archive: Path) -> dict[str, Any]:
    path = _sidecar_path(archive)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _amm_version() -> str:
    try:
        from importlib.metadata import version

        return version("aio-media-manager")
    except Exception:
        return ""
