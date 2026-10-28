"""Local nginx origin that rewrites CF-Connecting-IP → X-Forwarded-For for Jellyfin."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

from core.settings import Settings, settings
from core.supervisor import ProcessSupervisor, ProcessState, RestartPolicy

logger = logging.getLogger(__name__)

PROCESS_NAME = "jellyfin-cf-origin"
# Tunnel-only; not published on the NAS host. Jellyfin itself stays on its LAN port.
CF_ORIGIN_PORT = 8097
DEFAULT_TEMPLATE = Path("/etc/aio/nginx/jellyfin-cf-origin.conf.template")


class JellyfinCfOrigin:
    def __init__(
        self,
        app_settings: Settings | None = None,
        template_path: Path | None = None,
    ) -> None:
        self.settings = app_settings or settings
        self.template_path = template_path or DEFAULT_TEMPLATE

    def binary_path(self) -> str | None:
        return shutil.which("nginx")

    def runtime_config_path(self) -> Path:
        return self.settings.config_dir / "nginx" / "jellyfin-cf-origin.conf"

    def _process_state(self) -> str:
        try:
            return ProcessSupervisor.get().status(PROCESS_NAME).value
        except Exception:
            return ProcessState.STOPPED.value

    def status(self) -> dict[str, Any]:
        process = self._process_state()
        return {
            "process": process,
            "running": process == ProcessState.RUNNING.value,
            "binary_present": bool(self.binary_path()),
            "template_present": self.template_path.is_file(),
            "listen_port": CF_ORIGIN_PORT,
        }

    def render_config(self, *, upstream_port: int) -> Path:
        if not self.template_path.is_file():
            raise FileNotFoundError(f"nginx template missing: {self.template_path}")
        log_dir = self.settings.config_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        text = self.template_path.read_text(encoding="utf-8")
        rendered = (
            text.replace("__LISTEN_PORT__", str(CF_ORIGIN_PORT))
            .replace("__UPSTREAM_PORT__", str(int(upstream_port)))
            .replace("__ERROR_LOG__", str(log_dir / "jellyfin-cf-origin.err.log"))
            .replace("__ACCESS_LOG__", str(log_dir / "jellyfin-cf-origin.access.log"))
        )
        path = self.runtime_config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered, encoding="utf-8")
        return path

    def command(self, *, upstream_port: int) -> list[str] | None:
        exe = self.binary_path()
        if not exe:
            return None
        try:
            config = self.render_config(upstream_port=upstream_port)
        except OSError as exc:
            logger.warning("Could not render jellyfin CF origin nginx config: %s", exc)
            return None
        return [exe, "-g", "daemon off;", "-c", str(config)]

    async def start(self, *, upstream_port: int = 8096) -> dict[str, Any]:
        cmd = self.command(upstream_port=upstream_port)
        if not cmd:
            detail = "nginx missing" if not self.binary_path() else f"template missing: {self.template_path}"
            return {"status": "error", "detail": detail, **self.status()}
        supervisor = ProcessSupervisor.get()
        if supervisor.status(PROCESS_NAME) == ProcessState.RUNNING:
            await supervisor.stop(PROCESS_NAME)
        await supervisor.start(
            PROCESS_NAME,
            cmd,
            restart_policy=RestartPolicy.ALWAYS,
            log_dir=self.settings.config_dir / "logs",
        )
        logger.info(
            "Started Jellyfin Cloudflare origin on 127.0.0.1:%s → 127.0.0.1:%s",
            CF_ORIGIN_PORT,
            upstream_port,
        )
        return {"status": "started", "upstream_port": int(upstream_port), **self.status()}

    async def stop(self) -> dict[str, Any]:
        await ProcessSupervisor.get().stop(PROCESS_NAME)
        return {"status": "stopped", **self.status()}


jellyfin_cf_origin = JellyfinCfOrigin()


def jellyfin_tunnel_service_url() -> str:
    """Origin URL cloudflared should use for the published Jellyfin hostname."""
    return f"http://127.0.0.1:{CF_ORIGIN_PORT}"
