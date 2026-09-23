"""Shared *Arr (Prowlarr/Sonarr/Radarr) launch conventions."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Sequence

from applications.base import BaseApplication


class ArrApplication(BaseApplication):
    """Servarr apps share -nobrowser and -data flags plus /ping health."""

    def preferred_patterns(self) -> Sequence[str]:
        """Prefer glibc linux-core assets over linux-musl (Alpine) builds."""
        merged: list[str] = []
        for pattern in ("linux-core", *self.manifest.preferred_patterns):
            if pattern not in merged:
                merged.append(pattern)
        return tuple(merged)

    def build_start_command(self, executable: Path) -> list[str]:
        return [
            str(executable),
            "-nobrowser",
            f"-data={self.config_dir}",
        ]

    def working_directory(self) -> Path | None:
        exe = self.executable_path()
        if exe is not None:
            return exe.parent
        return self.install_dir

    def extra_env(self) -> dict[str, str]:
        env: dict[str, str] = {
            # Slim images need real ICU; invariant mode crashes Servarr culture lookups.
            "DOTNET_SYSTEM_GLOBALIZATION_INVARIANT": "0",
        }
        exe = self.executable_path()
        if exe is not None:
            parent = str(exe.parent)
            existing = os.environ.get("LD_LIBRARY_PATH", "")
            env["LD_LIBRARY_PATH"] = f"{parent}:{existing}" if existing else parent
        return env
