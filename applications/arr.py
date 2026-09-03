"""Shared *Arr (Prowlarr/Sonarr/Radarr) launch conventions."""

from __future__ import annotations

from pathlib import Path

from applications.base import BaseApplication


class ArrApplication(BaseApplication):
    """Servarr apps share -nobrowser and -data flags plus /ping health."""

    def build_start_command(self, executable: Path) -> list[str]:
        return [
            str(executable),
            "-nobrowser",
            f"-data={self.config_dir}",
        ]
