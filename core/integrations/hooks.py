"""Write starter configs for Recyclarr and NeutArr."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from core.recyclarr import write_recyclarr_config

logger = logging.getLogger(__name__)


def write_neutarr_config(
    config_dir: Path,
    *,
    sonarr_url: str,
    sonarr_key: str,
    radarr_url: str,
    radarr_key: str,
    lidarr_url: str = "",
    lidarr_key: str = "",
) -> Path:
    root = Path(config_dir)
    root.mkdir(parents=True, exist_ok=True)
    general = root / "general.json"
    if not general.exists():
        general.write_text(
            json.dumps(
                {
                    "debug_mode": False,
                    "log_refresh_interval_seconds": 30,
                    "ui_theme": "dark",
                    "check_for_updates": True,
                    "enable_notifications": False,
                    "notification_level": "info",
                    "local_access_bypass": True,
                    "proxy_auth_bypass": False,
                    "local_bypass_cidrs": [
                        "127.0.0.0/8",
                        "::1/128",
                        "10.0.0.0/8",
                        "172.16.0.0/12",
                        "192.168.0.0/16",
                    ],
                    "stateful_management_hours": 168,
                    "command_wait_delay": 1,
                    "command_wait_attempts": 600,
                    "minimum_download_queue_size": 1,
                    "api_timeout": 120,
                    "ssl_verify": False,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    _write_hunt_config(
        root / "sonarr.json",
        {
            "instances": [
                {
                    "name": "Sonarr (AMM)",
                    "api_url": sonarr_url,
                    "api_key": sonarr_key,
                    "enabled": bool(sonarr_url and sonarr_key),
                }
            ],
            "hunt_missing_items": 1,
            "hunt_upgrade_items": 1,
            "upgrade_mode": "episodes",
            "hunt_missing_mode": "episodes",
            "sleep_duration": 900,
            "monitored_only": True,
            "skip_future_episodes": True,
            "hourly_cap": 20,
        },
    )
    _write_hunt_config(
        root / "radarr.json",
        {
            "instances": [
                {
                    "name": "Radarr (AMM)",
                    "api_url": radarr_url,
                    "api_key": radarr_key,
                    "enabled": bool(radarr_url and radarr_key),
                }
            ],
            "hunt_missing_movies": 1,
            "hunt_upgrade_movies": 1,
            "sleep_duration": 900,
            "monitored_only": True,
            "skip_future_releases": True,
            "release_types": ["physical"],
            "release_type": "physical",
            "hourly_cap": 20,
        },
    )
    if lidarr_url:
        _write_hunt_config(
            root / "lidarr.json",
            {
                "instances": [
                    {
                        "name": "Lidarr (AMM)",
                        "api_url": lidarr_url,
                        "api_key": lidarr_key,
                        "enabled": bool(lidarr_key),
                    }
                ],
                "hunt_missing_mode": "artist",
                "hunt_missing_items": 1,
                "hunt_upgrade_items": 0,
                "sleep_duration": 900,
                "monitored_only": True,
                "hourly_cap": 20,
                "skip_future_releases": True,
            },
        )
    logger.info("Wrote NeutArr hunt configs under %s", root)
    return general


def _instance_is_wired(instance: object) -> bool:
    if not isinstance(instance, dict):
        return False
    return bool(str(instance.get("api_url") or "").strip() and str(instance.get("api_key") or "").strip())


def _write_hunt_config(path: Path, payload: dict[str, Any]) -> None:
    """Write a NeutArr app file, or fill one NeutArr already created empty.

    NeutArr copies default ``sonarr.json`` / ``radarr.json`` on startup, with a
    disabled instance named Default and no API key. Skipping those files leaves
    the app unwired. A file that already has a URL and key is left as-is.
    """
    if not path.exists():
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return
    try:
        current = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        current = {}
    if not isinstance(current, dict):
        current = {}
    instances = current.get("instances")
    if isinstance(instances, list) and any(_instance_is_wired(item) for item in instances):
        return
    desired = payload.get("instances") or []
    if not any(_instance_is_wired(item) for item in desired):
        return
    merged = dict(payload)
    merged.update({key: value for key, value in current.items() if key != "instances"})
    merged["instances"] = desired
    path.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
