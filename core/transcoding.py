"""Probe host GPU / VAAPI devices for media-server hardware transcoding."""

from __future__ import annotations

from pathlib import Path
from shutil import which
from typing import Any


def probe_transcoding() -> dict[str, Any]:
    dri = Path("/dev/dri")
    render_nodes = sorted(p.name for p in dri.glob("renderD*") if p.exists()) if dri.is_dir() else []
    cards = sorted(p.name for p in dri.glob("card*") if p.exists()) if dri.is_dir() else []
    vaapi = bool(render_nodes) or which("vainfo") is not None
    nvidia = Path("/dev/nvidia0").exists() or which("nvidia-smi") is not None
    intel_qsv = _module_loaded("i915")
    amd = Path("/dev/kfd").exists() or _module_loaded("amdgpu")
    available = vaapi or nvidia or intel_qsv or amd
    return {
        "available": available,
        "vaapi": vaapi,
        "intel_quicksync": intel_qsv or (vaapi and not nvidia and not amd),
        "amd": amd,
        "nvidia": nvidia,
        "dev_dri": dri.is_dir(),
        "render_nodes": render_nodes,
        "cards": cards,
        "ffmpeg": which("ffmpeg"),
        "notes": _notes(available, vaapi, nvidia),
    }


_SYS_MODULE = Path("/sys/module")


def _module_loaded(name: str) -> bool:
    # /sys/module/<name> exists while the kernel module is loaded. Its uevent file is write-only
    # (reading it raised PermissionError on a Synology with i915 and broke /api/system/info).
    return (_SYS_MODULE / name).is_dir()


def _notes(available: bool, vaapi: bool, nvidia: bool) -> str:
    if not available:
        return "No GPU transcoding devices detected. Jellyfin/Plex will use software encoding."
    if nvidia:
        return "NVIDIA device detected. Pass --gpus all (or /dev/nvidia*) into the AIO container."
    if vaapi:
        return "VAAPI/DRM device detected. Map /dev/dri into the AIO container."
    return "Hardware acceleration may be available; confirm device nodes inside the appliance."
