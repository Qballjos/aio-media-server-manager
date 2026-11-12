"""Self-contained Cleanuparr releases, supervised inside the appliance."""
from __future__ import annotations

import json
from pathlib import Path

from applications.base import SimpleApplication
from applications.manifest import AppCategory, AppManifest, AppTier, InstallMethod


class CleanuparrApp(SimpleApplication):
    manifest = AppManifest(
        name="cleanuparr",
        display_name="Cleanuparr",
        description="Cleans stalled and unwanted downloads in Sonarr, Radarr and Lidarr.",
        github_repo="Cleanuparr/Cleanuparr",
        upstream_url="https://cleanuparr.github.io/",
        tier=AppTier.OPTIONAL,
        category=AppCategory.MAINTENANCE,
        default_port=11011,
        executable_name="Cleanuparr",
        supported_architectures=("x86_64", "arm64"),
        install_method=InstallMethod.GITHUB_RELEASE,
        preferred_patterns=(r"linux-.*\.zip$",),
        optional_dependencies=("sonarr", "radarr", "lidarr", "qbittorrent", "sabnzbd"),
        health_path="/health/ready",
    )

    def extra_env(self) -> dict[str, str]:
        return {
            # Upstream otherwise ignores CLEANUPARR_CONFIG_PATH and shares /config.
            "DOTNET_RUNNING_IN_CONTAINER": "false",
            "CLEANUPARR_CONFIG_PATH": str(self.config_dir),
        }

    def post_install(self) -> None:
        self.apply_listen_port(self.port)
        self.prepare_browser_login()

    def working_directory(self) -> Path:
        executable = self.executable_path()
        return executable.parent if executable else self.install_dir

    def prepare_browser_login(self) -> bool:
        webroot = self.working_directory() / "wwwroot"
        if not webroot.is_dir():
            return False
        for suffix in ("html", "js"):
            source = Path(__file__).with_name(f"cleanuparr-login.{suffix}")
            (webroot / f"aio-login.{suffix}").write_bytes(source.read_bytes())
        return True

    def apply_listen_port(self, port: int) -> None:
        super().apply_listen_port(port)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        path = self.config_dir / "cleanuparr.json"
        data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        data.update(PORT=self.port, BIND_ADDRESS="0.0.0.0", BASE_PATH="")
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
