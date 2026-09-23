"""Optional Cloudflare Tunnel (remotely managed cloudflared) inside the appliance."""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from core.settings import Settings, settings
from core.supervisor import ProcessSupervisor, ProcessState, RestartPolicy

logger = logging.getLogger(__name__)

PROCESS_NAME = "cloudflared"


class CloudflareTunnelManager:
    def __init__(self, app_settings: Settings | None = None) -> None:
        self.settings = app_settings or settings

    @property
    def token_file(self) -> Path:
        path = self.settings.cloudflare_tunnel_token_file
        return Path(path) if path else self.settings.config_dir / "cloudflare" / "tunnel.token"

    def persist_token(self) -> Path | None:
        token = self.settings.cloudflare_tunnel_token
        path = self.token_file
        if token:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(token.strip() + "\n", encoding="utf-8")
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
            return path
        if path.is_file() and path.stat().st_size > 0:
            return path
        return None

    def token_present(self) -> bool:
        if self.settings.cloudflare_tunnel_token:
            return True
        path = self.token_file
        return path.is_file() and path.stat().st_size > 0

    def binary_path(self) -> str | None:
        return shutil.which("cloudflared")

    def _process_state(self) -> str:
        try:
            return ProcessSupervisor.get().status(PROCESS_NAME).value
        except Exception:
            return ProcessState.STOPPED.value

    def _metrics_ready(self) -> bool:
        addr = self.settings.cloudflare_tunnel_metrics_addr
        try:
            with urlopen(f"http://{addr}/ready", timeout=1) as response:
                return 200 <= response.status < 300
        except (URLError, OSError, TimeoutError, ValueError):
            return False

    def status(self) -> dict[str, Any]:
        running = self._process_state() == ProcessState.RUNNING.value
        ready = self._metrics_ready() if running else False
        return {
            "enabled": self.settings.cloudflare_tunnel_enabled,
            "token_present": self.token_present(),
            "token_file": str(self.token_file),
            "binary_present": bool(self.binary_path()),
            "process": self._process_state(),
            "connected": ready,
            "metrics_addr": self.settings.cloudflare_tunnel_metrics_addr,
            "origin": f"http://127.0.0.1:{self.settings.api_port}",
        }

    def command(self) -> list[str] | None:
        exe = self.binary_path()
        token_path = self.persist_token()
        if not exe or not token_path:
            return None
        return [
            exe,
            "tunnel",
            "--no-autoupdate",
            "--metrics",
            self.settings.cloudflare_tunnel_metrics_addr,
            "run",
            "--token-file",
            str(token_path),
        ]

    async def start(self) -> dict[str, Any]:
        if not self.settings.cloudflare_tunnel_enabled:
            return {"status": "disabled", **self.status()}
        cmd = self.command()
        if not cmd:
            detail = "cloudflared is not installed" if not self.binary_path() else "tunnel token missing"
            return {"status": "error", "detail": detail, **self.status()}
        supervisor = ProcessSupervisor.get()
        if supervisor.status(PROCESS_NAME) == ProcessState.RUNNING:
            return {"status": "running", **self.status()}
        await supervisor.start(
            PROCESS_NAME,
            cmd,
            restart_policy=RestartPolicy.ALWAYS,
            log_dir=self.settings.config_dir / "logs",
        )
        logger.info("Started Cloudflare Tunnel connector (cloudflared)")
        return {"status": "started", **self.status()}

    async def stop(self) -> dict[str, Any]:
        await ProcessSupervisor.get().stop(PROCESS_NAME)
        return {"status": "stopped", **self.status()}


cloudflare_tunnel = CloudflareTunnelManager()
