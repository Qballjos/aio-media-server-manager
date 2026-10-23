"""Pause and resume every download client at once, for a while or until resumed.

SABnzbd and NZBGet get their own timer, so they resume even if AIO is down. qBittorrent has
none, so the pause is kept in a file and the loop below resumes it; only torrents AIO stopped
start again, so ones you paused yourself stay paused.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

from core.settings import settings

logger = logging.getLogger(__name__)


def _state_path() -> Path:
    return Path(settings.config_dir) / "downloads-pause.json"


def _read_state() -> dict[str, Any] | None:
    try:
        data = json.loads(_state_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def pause_state() -> dict[str, Any]:
    data = _read_state()
    if data is None:
        return {"paused": False, "resume_at": None}
    return {"paused": True, "resume_at": data.get("resume_at")}


def _clients() -> dict[str, Any]:
    """Running download clients by name."""
    from applications.catalog import ApplicationCatalog
    from core.homepage import _running_names
    from core.integrations.credentials import get_application_api_key

    catalog = ApplicationCatalog()
    running = _running_names()
    clients: dict[str, Any] = {}
    if "sabnzbd" in running and catalog.has("sabnzbd"):
        from core.integrations.sabnzbd import SABnzbdClient

        plugin = catalog.get("sabnzbd")
        clients["sabnzbd"] = SABnzbdClient(port=plugin.port, api_key=get_application_api_key("sabnzbd", plugin.config_dir))
    if "nzbget" in running and catalog.has("nzbget"):
        from core.integrations.nzbget import NZBGetClient

        clients["nzbget"] = NZBGetClient(port=catalog.get("nzbget").port)
    if "qbittorrent" in running and catalog.has("qbittorrent"):
        from core.integrations.qbittorrent import QBittorrentClient

        client = QBittorrentClient(port=catalog.get("qbittorrent").port)
        if client.app_accessible() or client.login():
            clients["qbittorrent"] = client
    return clients


def _qbit(client: Any, action: str, hashes: list[str]) -> bool:
    """qBittorrent 5 calls it stop/start, 4 called it pause/resume."""
    if not hashes:
        return True
    legacy = {"stop": "pause", "start": "resume"}[action]
    for verb in (action, legacy):
        resp = client.session.post(f"{client.base_url}/torrents/{verb}", data={"hashes": "|".join(hashes)}, timeout=10)
        if resp.status_code != 404:
            return resp.status_code == 200
    return False


def pause_all(minutes: int | None = None) -> dict[str, Any]:
    previous = _read_state() or {}
    applied: dict[str, bool] = {}
    stopped: list[str] = list(previous.get("torrents") or [])
    for name, client in _clients().items():
        if name == "sabnzbd":
            res = client._request("config", {"name": "set_pause", "value": minutes}) if minutes else client._request("pause")
            applied[name] = res.get("status") is not False
        elif name == "nzbget":
            ok = client._call("pausedownload")
            if minutes:
                client._call("scheduleresume", [minutes * 60])
            applied[name] = bool(ok)
        else:
            rows = client.session.get(f"{client.base_url}/torrents/info", timeout=10).json()
            active = [
                row["hash"]
                for row in rows
                if isinstance(row, dict) and not str(row.get("state") or "").startswith(("paused", "stopped"))
            ]
            applied[name] = _qbit(client, "stop", active)
            stopped = sorted(set(stopped) | set(active))
    state = {"resume_at": time.time() + minutes * 60 if minutes else None, "torrents": stopped}
    _state_path().write_text(json.dumps(state), encoding="utf-8")
    logger.info("Paused downloads %s (%s).", f"for {minutes} min" if minutes else "until resumed", applied)
    return {"applied": applied, **pause_state()}


def resume_all() -> dict[str, Any]:
    state = _read_state() or {}
    applied: dict[str, bool] = {}
    for name, client in _clients().items():
        if name == "sabnzbd":
            applied[name] = client._request("resume").get("status") is not False
        elif name == "nzbget":
            applied[name] = bool(client._call("resumedownload"))
        else:
            applied[name] = _qbit(client, "start", list(state.get("torrents") or []))
    _state_path().unlink(missing_ok=True)
    logger.info("Resumed downloads (%s).", applied)
    return {"applied": applied, **pause_state()}


async def resume_when_due_loop(interval: float = 30.0) -> None:
    """Resume a timed pause once its time is up (also after a restart)."""
    while True:
        try:
            resume_at = pause_state().get("resume_at")
            if resume_at and time.time() >= float(resume_at):
                await asyncio.to_thread(resume_all)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Timed download resume failed: %s", exc)
        await asyncio.sleep(interval)
