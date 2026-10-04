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

    def read_token(self) -> str:
        token = (self.settings.cloudflare_tunnel_token or "").strip()
        if token:
            return token
        path = self.token_file
        if path.is_file():
            try:
                return path.read_text(encoding="utf-8").strip()
            except OSError:
                return ""
        return ""

    def token_present(self) -> bool:
        return bool(self.read_token())

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
        process = self._process_state()
        running = process == ProcessState.RUNNING.value
        ready = self._metrics_ready() if running else False
        has_token = self.token_present()
        return {
            "enabled": self.settings.cloudflare_tunnel_enabled,
            "token_present": has_token,
            "token_saved": has_token,
            "token_file": str(self.token_file),
            "binary_present": bool(self.binary_path()),
            "process": process,
            "running": running,
            "connected": ready,
            "metrics_addr": self.settings.cloudflare_tunnel_metrics_addr,
            "origin": f"http://127.0.0.1:{self.settings.api_port}",
            "summary": self._summary(has_token=has_token, running=running, ready=ready),
        }

    def _summary(self, *, has_token: bool, running: bool, ready: bool) -> str:
        if not self.settings.cloudflare_tunnel_enabled:
            return "Off"
        if not has_token:
            return "Enabled — token missing"
        if not self.binary_path():
            return "Enabled — cloudflared binary missing"
        if ready:
            return "Connected"
        if running:
            return "Connector running — waiting for Cloudflare"
        return "Enabled — connector not running"

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
