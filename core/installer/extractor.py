"""
core/installer/extractor.py — Safe Multi-Format Archive Extractor

Extracts .tar.gz, .tar.xz, .zip, .deb, and raw binaries with:
  - Protection against directory traversal (Zip-Slip, symlink escapes)
  - Automatic single top-level directory wrapper stripping
  - Preservation and enforcement of Unix executable permissions
"""

from __future__ import annotations

import io
import logging
import os
import shutil
import stat
import subprocess
import tarfile
import zipfile
from pathlib import Path

logger = logging.getLogger(__name__)


class ExtractionSecurityError(ValueError):
    """Raised when an archive member attempts a path traversal or security escape."""


class ArchiveExtractor:
    """
    Safely extracts archives to a target directory.
    """

    @classmethod
    def extract(
        cls,
        archive_path: Path,
        destination_dir: Path,
        strip_single_wrapper: bool = True,
    ) -> Path:
        """
        Extract archive_path into destination_dir.
        Returns the resolved destination directory.
        """
        archive_path = Path(archive_path).resolve()
        destination_dir = Path(destination_dir).resolve()
        destination_dir.mkdir(parents=True, exist_ok=True)

        if not archive_path.is_file():
            raise FileNotFoundError(f"Archive file not found: {archive_path}")

        name = archive_path.name.lower()

        if name.endswith((".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz", ".tar")):
            cls._extract_tar(archive_path, destination_dir)
        elif name.endswith(".zip"):
            cls._extract_zip(archive_path, destination_dir)
        elif name.endswith(".deb"):
            cls._extract_deb(archive_path, destination_dir)
        else:
            # Assume raw single binary
            cls._extract_raw_binary(archive_path, destination_dir)

        if strip_single_wrapper:
            cls._strip_single_root_dir(destination_dir)

        return destination_dir

    # ------------------------------------------------------------------
    # Security checks
    # ------------------------------------------------------------------

    @staticmethod
    def _is_safe_path(base_dir: Path, path: Path) -> bool:
        """Verify that resolved path stays strictly within base_dir."""
        try:
            base = base_dir.resolve()
            resolved = path.resolve()
            return resolved == base or str(resolved).startswith(str(base) + os.sep)
        except (ValueError, RuntimeError):
            return False

    # ------------------------------------------------------------------
    # TAR extraction
    # ------------------------------------------------------------------

    @classmethod
    def _extract_tar(cls, archive_path: Path, target_dir: Path) -> None:
        with tarfile.open(archive_path, "r:*") as tar:
            for member in tar.getmembers():
                dest_path = (target_dir / member.name).resolve()
                if not cls._is_safe_path(target_dir, dest_path):
                    raise ExtractionSecurityError(
                        f"Archive member attempts path traversal: {member.name}"
                    )
                # Filter out dangerous symlinks pointing outside
                if member.issym() or member.islnk():
                    link_target = (dest_path.parent / member.linkname).resolve()
                    if not cls._is_safe_path(target_dir, link_target):
                        raise ExtractionSecurityError(
                            f"Archive link points outside target directory: {member.name} -> {member.linkname}"
                        )

            # Python 3.12+ supports filter='data'
            if hasattr(tarfile, "data_filter"):
                tar.extractall(path=target_dir, filter="data")
            else:
                tar.extractall(path=target_dir)

    # ------------------------------------------------------------------
    # ZIP extraction
    # ------------------------------------------------------------------

    @classmethod
    def _extract_zip(cls, archive_path: Path, target_dir: Path) -> None:
        with zipfile.ZipFile(archive_path, "r") as zf:
            for member in zf.infolist():
                dest_path = (target_dir / member.filename).resolve()
                if not cls._is_safe_path(target_dir, dest_path):
                    raise ExtractionSecurityError(
                        f"Zip member attempts path traversal: {member.filename}"
                    )

                # Extract and preserve Unix permissions if recorded
                extracted_path = Path(zf.extract(member, path=target_dir))
                # Zip permissions are in top 16 bits of external_attr
                unix_mode = member.external_attr >> 16
                if unix_mode and extracted_path.exists():
                    try:
                        extracted_path.chmod(unix_mode & 0o777)
                    except OSError:
                        pass

    # ------------------------------------------------------------------
    # DEB extraction
    # ------------------------------------------------------------------

    @classmethod
    def _extract_deb(cls, archive_path: Path, target_dir: Path) -> None:
        """
        Extract a Debian package (.deb).
        Tries dpkg-deb first if available; otherwise parses the ar archive to extract data.tar.*.
        """
        if shutil.which("dpkg-deb"):
            try:
                res = subprocess.run(
                    ["dpkg-deb", "-x", str(archive_path), str(target_dir)],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                if res.returncode == 0:
                    return
            except subprocess.SubprocessError as exc:
                logger.debug("dpkg-deb failed, falling back to built-in ar extractor: %s", exc)

        cls._extract_deb_builtin(archive_path, target_dir)

    @classmethod
    def _extract_deb_builtin(cls, deb_path: Path, target_dir: Path) -> None:
        """
        Extracts data.tar.* from an ar/deb container using standard library file operations.
        """
        with open(deb_path, "rb") as fh:
            magic = fh.read(8)
            if magic != b"!<arch>\n":
                raise ValueError(f"Not a valid Debian (.deb) or ar archive: {deb_path.name}")

            while True:
                header = fh.read(60)
                if len(header) < 60:
                    break
                filename = header[:16].decode("ascii", errors="ignore").strip().rstrip("/")
                try:
                    file_size = int(header[48:58].decode("ascii", errors="ignore").strip())
                except ValueError:
                    break

                # The application payload is in data.tar.*
                if filename.startswith("data.tar"):
                    data_bytes = fh.read(file_size)
                    with tarfile.open(fileobj=io.BytesIO(data_bytes), mode="r:*") as data_tar:
                        for member in data_tar.getmembers():
                            dest_path = (target_dir / member.name).resolve()
                            if not cls._is_safe_path(target_dir, dest_path):
                                raise ExtractionSecurityError(
                                    f"Deb data archive attempts path traversal: {member.name}"
                                )
                        if hasattr(tarfile, "data_filter"):
                            data_tar.extractall(path=target_dir, filter="data")
                        else:
                            data_tar.extractall(path=target_dir)
                    return

                # Advance past content (ar aligns to 2-byte boundaries)
                fh.seek(file_size + (file_size % 2), io.SEEK_CUR)

        raise ValueError(f"No data.tar archive found inside Debian package {deb_path.name}")

    # ------------------------------------------------------------------
    # Raw single binary
    # ------------------------------------------------------------------

    @classmethod
    def _extract_raw_binary(cls, binary_path: Path, target_dir: Path) -> None:
        target_file = target_dir / binary_path.name
        shutil.copy2(binary_path, target_file)
        # Make executable
        mode = target_file.stat().st_mode
        target_file.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    # ------------------------------------------------------------------
    # Wrapper stripping
    # ------------------------------------------------------------------

    @classmethod
    def _strip_single_root_dir(cls, target_dir: Path) -> None:
        """
        If target_dir contains exactly one directory and no files, move all its
        contents up to target_dir and remove the wrapper directory.
        """
        entries = list(target_dir.iterdir())
        if len(entries) == 1 and entries[0].is_dir():
            wrapper = entries[0]
            # Don't strip if it looks like a system root hierarchy (e.g. usr/, etc/)
            if wrapper.name in ("usr", "etc", "opt", "var"):
                return

            logger.debug("Stripping single top-level directory '%s' from extraction", wrapper.name)
            temp_wrapper = target_dir.parent / f".{target_dir.name}_temp_wrapper"
            wrapper.rename(temp_wrapper)
            try:
                for item in temp_wrapper.iterdir():
                    shutil.move(str(item), str(target_dir / item.name))
            finally:
                shutil.rmtree(temp_wrapper, ignore_errors=True)
