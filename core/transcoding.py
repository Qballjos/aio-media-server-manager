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
    intel_qsv = any("i915" in p.read_text(encoding="utf-8", errors="ignore") for p in _mod_aliases())
    amd = Path("/dev/kfd").exists() or any("amdgpu" in p.read_text(encoding="utf-8", errors="ignore") for p in _mod_aliases())
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


def _mod_aliases() -> list[Path]:
    root = Path("/sys/module")
    if not root.is_dir():
        return []
    return [root / name / "uevent" for name in ("i915", "amdgpu", "nvidia") if (root / name).exists()]


def _notes(available: bool, vaapi: bool, nvidia: bool) -> str:
    if not available:
        return "No GPU transcoding devices detected. Jellyfin/Plex will use software encoding."
    if nvidia:
        return "NVIDIA device detected. Pass --gpus all (or /dev/nvidia*) into the AIO container."
    if vaapi:
        return "VAAPI/DRM device detected. Map /dev/dri into the AIO container."
    return "Hardware acceleration may be available; confirm device nodes inside the appliance."
