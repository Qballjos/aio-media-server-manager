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

    _write_json_if_missing(
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
    _write_json_if_missing(
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
        _write_json_if_missing(
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


def _write_json_if_missing(path: Path, payload: dict[str, Any]) -> None:
    if path.exists():
        return
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
