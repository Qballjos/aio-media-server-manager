"""Shared install helpers for source-based catalog plugins."""

from __future__ import annotations

import shutil
import stat
import subprocess
import sys
from pathlib import Path


def write_runner(path: Path, lines: list[str]) -> Path:
    """Write an executable launch script.

    GitHub source zips often unpack a package directory named after the app
    (``bazarr/``, ``sabnzbd/``). If *path* is already that directory, write
    ``run-{name}`` beside it instead of failing with EISDIR.
    """
    target = path
    if target.exists() and not target.is_file():
        target = path.parent / f"run-{path.name}"
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return target


def create_venv(install_root: Path) -> Path:
    venv_dir = install_root / "venv"
    subprocess.run(
        [sys.executable, "-m", "venv", str(venv_dir)],
        check=True,
        capture_output=True,
        text=True,
    )
    pip = venv_bin(venv_dir, "pip")
    subprocess.run(
        [str(pip), "install", "--upgrade", "pip"],
        check=True,
        capture_output=True,
        text=True,
    )
    return venv_dir


def venv_bin(venv_dir: Path, name: str) -> Path:
    posix = venv_dir / "bin" / name
    if posix.is_file():
        return posix
    windows = venv_dir / "Scripts" / f"{name}.exe"
    if windows.is_file():
        return windows
    alt = venv_dir / "Scripts" / name
    return alt if alt.is_file() else posix


def python_bin() -> str:
    return sys.executable


def launch_argv(executable: Path, extra: list[str] | None = None) -> list[str]:
    """Build an argv that can actually execve the target.

    Python sources (``bazarr.py``, ``SABnzbd.py``) are not ELF binaries; starting
    them without an interpreter yields ``OSError: [Errno 8] Exec format error``.
    """
    extra = extra or []
    if executable.suffix.lower() == ".py":
        return [python_bin(), str(executable), *extra]
    return [str(executable), *extra]


def npm_bin() -> str | None:
    return shutil.which("npm")


def node_bin() -> str | None:
    return shutil.which("node")
