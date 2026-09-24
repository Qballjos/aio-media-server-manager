"""Persisted per-application preferences (listen port, autostart)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from core.settings import Settings, settings

logger = logging.getLogger(__name__)

_PREFS_NAME = "app_prefs.json"
_MIN_PORT = 1024
_MAX_PORT = 65535


class AppPrefsError(ValueError):
    """Invalid application preference."""


def prefs_path(app_settings: Settings | None = None) -> Path:
    return (app_settings or settings).config_dir / _PREFS_NAME


def load_prefs(app_settings: Settings | None = None) -> dict[str, Any]:
    empty = {"ports": {}, "autostart": {}, "options": {}}
    path = prefs_path(app_settings)
    if not path.is_file():
        return empty
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as err:
        logger.warning("Could not read %s: %s", path, err)
        return empty
    ports = data.get("ports") if isinstance(data, dict) else {}
    autostart = data.get("autostart") if isinstance(data, dict) else {}
    clean_ports: dict[str, int] = {}
    if isinstance(ports, dict):
        for name, port in ports.items():
            try:
                clean_ports[str(name)] = int(port)
            except (TypeError, ValueError):
                continue
    clean_auto: dict[str, bool] = {}
    if isinstance(autostart, dict):
        for name, flag in autostart.items():
            clean_auto[str(name)] = bool(flag)
    clean_options: dict[str, dict[str, Any]] = {}
    raw_options = data.get("options") if isinstance(data, dict) else {}
    if isinstance(raw_options, dict):
        for app_name, flags in raw_options.items():
            if isinstance(flags, dict):
                clean_options[str(app_name)] = dict(flags)
    return {"ports": clean_ports, "autostart": clean_auto, "options": clean_options}


def save_prefs(data: dict[str, Any], app_settings: Settings | None = None) -> None:
    cfg = app_settings or settings
    cfg.config_dir.mkdir(parents=True, exist_ok=True)
    path = prefs_path(cfg)
    options: dict[str, dict[str, Any]] = {}
    for app_name, flags in (data.get("options") or {}).items():
        if isinstance(flags, dict):
            options[str(app_name)] = dict(flags)
    payload = {
        "ports": {name: int(port) for name, port in (data.get("ports") or {}).items()},
        "autostart": {name: bool(flag) for name, flag in (data.get("autostart") or {}).items()},
        "options": options,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def load_app_ports(app_settings: Settings | None = None) -> dict[str, int]:
    return dict(load_prefs(app_settings)["ports"])


def autostart_for(name: str, *, default: bool = True, app_settings: Settings | None = None) -> bool:
    flags = load_prefs(app_settings)["autostart"]
    if name not in flags:
        return default
    return bool(flags[name])


def app_option(name: str, key: str, *, default: bool = False, app_settings: Settings | None = None) -> bool:
    flags = (load_prefs(app_settings).get("options") or {}).get(name) or {}
    if key not in flags:
        return default
    return bool(flags[key])


def set_app_option(name: str, key: str, value: Any, *, app_settings: Settings | None = None) -> dict[str, Any]:
    data = load_prefs(app_settings)
    options = data.setdefault("options", {})
    app_flags = dict(options.get(name) or {})
    app_flags[key] = value
    options[name] = app_flags
    data["options"] = options
    save_prefs(data, app_settings)
    return data


def validate_port(port: int, *, reserved: set[int] | None = None) -> int:
    value = int(port)
    if value < _MIN_PORT or value > _MAX_PORT:
        raise AppPrefsError(f"Port must be between {_MIN_PORT} and {_MAX_PORT}.")
    if reserved and value in reserved:
        raise AppPrefsError(f"Port {value} is reserved by the manager.")
    return value


def update_app_prefs(
    name: str,
    *,
    port: int | None = None,
    autostart: bool | None = None,
    reserved_ports: set[int] | None = None,
    taken_by: dict[str, int] | None = None,
    app_settings: Settings | None = None,
) -> dict[str, Any]:
    data = load_prefs(app_settings)
    if port is not None:
        value = validate_port(port, reserved=reserved_ports)
        for other, assigned in (taken_by or {}).items():
            if other != name and int(assigned) == value:
                raise AppPrefsError(f"Port {value} is already assigned to {other}.")
        data["ports"][name] = value
    if autostart is not None:
        data["autostart"][name] = bool(autostart)
    save_prefs(data, app_settings)
    return data
