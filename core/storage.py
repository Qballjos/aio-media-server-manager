"""
core/storage.py — Storage & Permission Abstractions

Provides:
  - StorageManager : path validation, hardlink detection, filesystem type
                     detection, permission application, standard directory
                     layout creation.

Usage
-----
    from core.storage import StorageManager
    from core.settings import settings

    sm = StorageManager(settings)
    sm.validate_all()
    sm.create_standard_layout()
"""

from __future__ import annotations

import ctypes
import logging
import os
import platform
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from core.library_layout import LibraryLayout

logger = logging.getLogger(__name__)

_hardlink_warning_logged = False

# ---------------------------------------------------------------------------
# Filesystem type helpers
# ---------------------------------------------------------------------------

# Filesystem types considered "network" — warn the user about potential issues
# (slow chown, no hardlink support, different permission semantics).
_NETWORK_FS_TYPES = frozenset(
    {
        "9p",
        "ceph",
        "cifs",
        "davfs",
        "davfs2",
        "glusterfs",
        "lustre",
        "nfs",
        "nfs4",
        "smb3",
        "sshfs",
        "vboxsf",  # VirtualBox shared folder
    }
)

# FUSE filesystem types — usually support hardlinks but worth flagging
_FUSE_FS_TYPES = frozenset({"fuse", "fuse.mergerfs", "fuse.rclone"})


@dataclass
class PathInfo:
    path: Path
    exists: bool
    is_dir: bool
    writable: bool
    fs_type: str
    is_network_fs: bool
    is_fuse_fs: bool
    hardlinks_supported: Optional[bool]  # None = not checked


# ---------------------------------------------------------------------------
# StorageManager
# ---------------------------------------------------------------------------


class StorageManager:
    """
    Validates paths, checks permissions, detects filesystem capabilities,
    and creates the standard directory layout.
    """

    def __init__(self, settings) -> None:  # type: ignore[annotation-unchecked]
        self._settings = settings
        self._path_info: dict[str, PathInfo] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate_all(self) -> dict[str, PathInfo]:
        """
        Validate config_dir, download_dir, and media_dir.
        Returns a mapping of label → PathInfo.
        Logs warnings for any problems found.
        """
        s = self._settings
        paths = {
            "config_dir": s.config_dir,
            "download_dir": s.download_dir,
            "media_dir": s.media_dir,
        }
        for label, path in paths.items():
            info = self._inspect_path(path, label)
            self._path_info[label] = info
            self._log_path_info(label, info)

        # Hardlink check between download and media dirs
        dl_info = self._path_info.get("download_dir")
        media_info = self._path_info.get("media_dir")
        if dl_info and media_info and dl_info.exists and media_info.exists:
            supported = self._check_hardlink_support(
                self._settings.download_dir, self._settings.media_dir
            )
            dl_info.hardlinks_supported = supported
            if not supported:
                global _hardlink_warning_logged
                if not _hardlink_warning_logged:
                    logger.warning(
                        "Hardlinks are NOT supported between '%s' and '%s'. "
                        "*Arr will copy files instead of linking. Bind one host folder "
                        "as /data (same filesystem and btrfs subvolume) and set "
                        "AMM_DOWNLOAD_DIR=/data/downloads AMM_MEDIA_DIR=/data/media.",
                        self._settings.download_dir,
                        self._settings.media_dir,
                    )
                    _hardlink_warning_logged = True
            else:
                logger.info(
                    "Hardlinks are supported between download_dir and media_dir. ✓"
                )

        return self._path_info

    def create_standard_layout(self) -> LibraryLayout:
        """
        Create the canonical directory tree under config_dir, download_dir,
        media_dir, and cache_dir. Directories are created with correct ownership.
        """
        puid = self._settings.puid
        pgid = self._settings.pgid
        layout = LibraryLayout.from_settings(self._settings)

        dirs_to_create = [
            self._settings.config_dir / "logs",
            self._settings.install_dir,
            self._settings.cache_dir,
            self._settings.cache_dir / "downloads",
            *layout.directories(),
        ]

        for directory in dirs_to_create:
            self.ensure_dir(directory, puid, pgid)

        logger.info("Standard directory layout created/verified.")
        return layout

    def validate_path(self, path: Path, label: str) -> PathInfo:
        """Inspect and return a PathInfo for the given path."""
        info = self._inspect_path(path, label)
        self._log_path_info(label, info)
        return info

    def apply_permissions(
        self,
        path: Path,
        puid: int,
        pgid: int,
        *,
        recursive: bool = False,
    ) -> None:
        """
        Apply puid/pgid ownership to path.  If recursive=True, walk the tree.
        Skips entries that already have the correct owner to minimise I/O.
        """
        path = Path(path)
        if recursive:
            for root, dirs, files in os.walk(path):
                for entry_name in [root] + [os.path.join(root, f) for f in files + dirs]:
                    _safe_chown(Path(entry_name), puid, pgid)
        else:
            _safe_chown(path, puid, pgid)

    def ensure_dir(self, path: Path, puid: int, pgid: int) -> None:
        """
        Create directory (including parents) and apply ownership.
        Safe to call if the directory already exists.
        """
        path = Path(path)
        try:
            path.mkdir(parents=True, exist_ok=True)
            _safe_chown(path, puid, pgid)
            logger.debug("Directory ready: %s", path)
        except OSError as exc:
            logger.warning("Could not create directory %s: %s", path, exc)

    def get_path_info(self) -> dict[str, PathInfo]:
        """Return cached path info (populated after validate_all())."""
        return dict(self._path_info)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _inspect_path(path: Path, label: str) -> PathInfo:
        path = Path(path)
        exists = path.exists()
        is_dir = path.is_dir() if exists else False

        # Writable check
        writable = False
        if exists and is_dir:
            try:
                test_file = path / ".amm_write_test"
                test_file.touch()
                test_file.unlink()
                writable = True
            except OSError:
                writable = False

        fs_type = _detect_fs_type(path)
        is_network = fs_type in _NETWORK_FS_TYPES
        is_fuse = fs_type in _FUSE_FS_TYPES

        return PathInfo(
            path=path,
            exists=exists,
            is_dir=is_dir,
            writable=writable,
            fs_type=fs_type,
            is_network_fs=is_network,
            is_fuse_fs=is_fuse,
            hardlinks_supported=None,
        )

    @staticmethod
    def _check_hardlink_support(src_dir: Path, dst_dir: Path) -> bool:
        """
        Create a temporary file in src_dir and attempt os.link() into dst_dir.
        Returns True if hardlinks work across the two directories.
        """
        try:
            with tempfile.NamedTemporaryFile(
                dir=str(src_dir), delete=False, suffix=".amm_hl_test"
            ) as tmp:
                src_path = Path(tmp.name)
            dst_path = dst_dir / (src_path.name + ".link")
            try:
                os.link(str(src_path), str(dst_path))
                dst_path.unlink()
                return True
            except OSError:
                return False
            finally:
                try:
                    src_path.unlink()
                except OSError:
                    pass
        except Exception as exc:  # noqa: BLE001
            logger.debug("Hardlink test failed with exception: %s", exc)
            return False

    @staticmethod
    def _log_path_info(label: str, info: PathInfo) -> None:
        if not info.exists:
            logger.warning(
                "[%s] Path does not exist: %s", label, info.path
            )
        elif not info.is_dir:
            logger.error(
                "[%s] Path is not a directory: %s", label, info.path
            )
        elif not info.writable:
            logger.error(
                "[%s] Path is not writable: %s — check PUID/PGID permissions.",
                label,
                info.path,
            )
        else:
            extras = []
            if info.is_network_fs:
                extras.append(f"⚠ network filesystem ({info.fs_type})")
            elif info.is_fuse_fs:
                extras.append(f"ℹ FUSE filesystem ({info.fs_type})")
            extra_str = "  " + "  ".join(extras) if extras else ""
            logger.info("[%s] %s  [%s]%s ✓", label, info.path, info.fs_type, extra_str)


# ---------------------------------------------------------------------------
# Filesystem type detection
# ---------------------------------------------------------------------------


def _detect_fs_type(path: Path) -> str:
    """
    Detect the filesystem type for the given path.

    Strategy:
      1. Linux: parse /proc/mounts
      2. macOS: use statfs(2) via ctypes
      3. Fallback: 'unknown'
    """
    system = platform.system()
    if system == "Linux":
        return _fs_type_linux(path)
    if system == "Darwin":
        return _fs_type_macos(path)
    return "unknown"


def _fs_type_linux(path: Path) -> str:
    """Parse /proc/mounts to find the filesystem type for path."""
    try:
        resolved = str(path.resolve())
        best_mount = ""
        best_type = "unknown"
        with open("/proc/mounts", encoding="utf-8") as fh:
            for line in fh:
                parts = line.split()
                if len(parts) < 3:
                    continue
                mountpoint = parts[1]
                fs_type = parts[2]
                # Match the longest (most specific) mountpoint prefix
                if resolved.startswith(mountpoint) and len(mountpoint) > len(best_mount):
                    best_mount = mountpoint
                    best_type = fs_type
        return best_type
    except OSError:
        return "unknown"


def _fs_type_macos(path: Path) -> str:
    """Use statfs(2) via ctypes on macOS to retrieve filesystem type."""
    try:
        # struct statfs layout on macOS includes f_fstypename at a fixed offset
        # Use os.statvfs which doesn't expose type name, so we use ctypes.
        MFSNAMELEN = 16

        class StatFS(ctypes.Structure):
            _fields_ = [
                ("f_bsize", ctypes.c_uint32),
                ("f_iosize", ctypes.c_int32),
                ("f_blocks", ctypes.c_uint64),
                ("f_bfree", ctypes.c_uint64),
                ("f_bavail", ctypes.c_uint64),
                ("f_files", ctypes.c_uint64),
                ("f_ffree", ctypes.c_uint64),
                ("f_fsid", ctypes.c_int64),
                ("f_owner", ctypes.c_uint32),
                ("f_type", ctypes.c_uint32),
                ("f_flags", ctypes.c_uint64),
                ("f_fssubtype", ctypes.c_uint32),
                ("f_fstypename", ctypes.c_char * MFSNAMELEN),
                # Remaining fields omitted — we only need f_fstypename
                ("_pad", ctypes.c_char * 512),
            ]

        buf = StatFS()
        libc = ctypes.CDLL("libc.dylib", use_errno=True)
        ret = libc.statfs(str(path).encode(), ctypes.byref(buf))
        if ret == 0:
            return buf.f_fstypename.decode("utf-8", errors="replace").rstrip("\x00")
        return "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def _safe_chown(path: Path, uid: int, gid: int) -> None:
    """chown path if ownership doesn't already match.  Silently skips on error."""
    try:
        st = os.stat(path)
        if st.st_uid == uid and st.st_gid == gid:
            return
        os.chown(path, uid, gid)
    except FileNotFoundError:
        pass
    except PermissionError:
        logger.debug("No permission to chown %s — skipping.", path)
    except OSError as exc:
        logger.warning("chown failed for %s: %s", path, exc)
