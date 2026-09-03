"""
core/installer/arch.py — System Architecture & Platform Detection

Detects the host OS, CPU architecture, and matches asset filenames from
GitHub Releases or external sources against target platform requirements.
"""

from __future__ import annotations

import enum
import logging
import platform
import re
from typing import Sequence

logger = logging.getLogger(__name__)


class PlatformArch(str, enum.Enum):
    X86_64 = "x86_64"
    ARM64 = "arm64"
    ARMV7 = "armv7"
    UNKNOWN = "unknown"


class PlatformOS(str, enum.Enum):
    LINUX = "linux"
    DARWIN = "darwin"
    WINDOWS = "windows"
    UNKNOWN = "unknown"


def detect_system_arch() -> PlatformArch:
    """
    Detect the machine's hardware architecture normalized to PlatformArch.
    """
    machine = platform.machine().lower().strip()
    if machine in ("x86_64", "amd64", "x64"):
        return PlatformArch.X86_64
    if machine in ("aarch64", "arm64", "armv8b", "armv8l"):
        return PlatformArch.ARM64
    if machine in ("armv7l", "armv7", "armhf", "arm"):
        return PlatformArch.ARMV7
    logger.warning("Unrecognized CPU architecture: %s", machine)
    return PlatformArch.UNKNOWN


def detect_system_os() -> PlatformOS:
    """
    Detect the operating system normalized to PlatformOS.
    """
    system = platform.system().lower().strip()
    if system == "linux":
        return PlatformOS.LINUX
    if system == "darwin":
        return PlatformOS.DARWIN
    if system == "windows":
        return PlatformOS.WINDOWS
    logger.warning("Unrecognized operating system: %s", system)
    return PlatformOS.UNKNOWN


# Regex patterns matching architectures in release asset filenames
_ARCH_PATTERNS: dict[PlatformArch, list[re.Pattern[str]]] = {
    PlatformArch.X86_64: [
        re.compile(r"(?:^|[-_.])(?:x86_64|amd64|x64|linux64|x86-64)(?:[-_.]|$)", re.IGNORECASE),
        re.compile(r"[-_]core[-_]x64(?:[-_.]|$)", re.IGNORECASE),
        re.compile(r"[-_]netcore[-_]linux[-_]x64(?:[-_.]|$)", re.IGNORECASE),
    ],
    PlatformArch.ARM64: [
        re.compile(r"(?:^|[-_.])(?:arm64|aarch64|armv8)(?:[-_.]|$)", re.IGNORECASE),
        re.compile(r"[-_]core[-_]arm64(?:[-_.]|$)", re.IGNORECASE),
        re.compile(r"[-_]netcore[-_]linux[-_]arm64(?:[-_.]|$)", re.IGNORECASE),
    ],
    PlatformArch.ARMV7: [
        re.compile(r"(?:^|[-_.])(?:armv7l?|armhf|arm32)(?:[-_.]|$)", re.IGNORECASE),
        re.compile(r"[-_]core[-_]arm(?:[-_.]|$)", re.IGNORECASE),
    ],
}

# Negative matches to avoid false positives (e.g. matching x86_64 when arm64 is in the name)
_NEGATIVE_PATTERNS: dict[PlatformArch, list[re.Pattern[str]]] = {
    PlatformArch.X86_64: [
        re.compile(r"arm64|aarch64|armv7|armhf", re.IGNORECASE),
    ],
    PlatformArch.ARM64: [
        re.compile(r"x86_64|amd64|x64(?![-_]?arm)", re.IGNORECASE),
    ],
    PlatformArch.ARMV7: [
        re.compile(r"arm64|aarch64|x86_64|amd64", re.IGNORECASE),
    ],
}

_OS_PATTERNS: dict[PlatformOS, list[re.Pattern[str]]] = {
    PlatformOS.LINUX: [
        re.compile(r"(?:^|[-_.])linux(?:[-_.]|$)", re.IGNORECASE),
        re.compile(r"\.deb$|\.tar\.gz$|\.tgz$|\.tar\.xz$", re.IGNORECASE),
    ],
    PlatformOS.DARWIN: [
        re.compile(r"(?:^|[-_.])(?:osx|darwin|macos)(?:[-_.]|$)", re.IGNORECASE),
    ],
    PlatformOS.WINDOWS: [
        re.compile(r"(?:^|[-_.])(?:windows|win)(?:[-_.]|$)", re.IGNORECASE),
        re.compile(r"\.exe$|\.msi$", re.IGNORECASE),
    ],
}


def matches_arch_pattern(filename: str, arch: PlatformArch) -> bool:
    """
    Check whether an asset filename matches the specified CPU architecture.
    """
    if arch == PlatformArch.UNKNOWN:
        return False

    # Check negative patterns first to prevent ambiguous matches
    for neg in _NEGATIVE_PATTERNS.get(arch, []):
        if neg.search(filename):
            return False

    # Check positive patterns
    for pattern in _ARCH_PATTERNS.get(arch, []):
        if pattern.search(filename):
            return True

    return False


def score_asset_match(
    filename: str,
    arch: PlatformArch,
    target_os: PlatformOS = PlatformOS.LINUX,
    preferred_extensions: Sequence[str] = (".tar.gz", ".tgz", ".tar.xz", ".zip", ".deb"),
) -> int:
    """
    Score how well an asset filename fits the target architecture, OS, and format.
    Higher score is better. A score < 0 means incompatible.
    """
    name_lower = filename.lower()

    # Reject obvious non-binary files (sources, checksums, signatures)
    if name_lower.endswith((".sha256", ".sha512", ".asc", ".sig", ".md5", ".txt", ".json")):
        return -1
    if "source" in name_lower or "symbols" in name_lower:
        return -1

    # Check architecture
    if not matches_arch_pattern(filename, arch):
        return -1

    score = 100

    # Match OS
    if target_os == PlatformOS.LINUX:
        # Avoid windows or macos builds
        if any(w in name_lower for w in ("windows", "win32", "win64", ".exe", ".msi", "macos", "osx", "darwin")):
            return -1
        if "linux" in name_lower:
            score += 50
    elif target_os == PlatformOS.DARWIN:
        if any(w in name_lower for w in ("windows", "linux")):
            return -1
        if any(w in name_lower for w in ("macos", "osx", "darwin")):
            score += 50

    # Extension preferences
    for rank, ext in enumerate(preferred_extensions):
        if name_lower.endswith(ext):
            score += (len(preferred_extensions) - rank) * 10
            break

    # Avoid debug builds
    if "debug" in name_lower:
        score -= 30

    return score
