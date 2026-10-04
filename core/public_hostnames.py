"""Per-app public subdomains for Open UI / Cloudflare Tunnel publishing."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from core.settings import Settings, settings

logger = logging.getLogger(__name__)

_FILE_NAME = "public_hostnames.json"
_SUBDOMAIN_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
MANAGER_KEY = "manager"

# Apps that are rarely useful as public browser UIs.
_SKIP_PUBLIC_UI = frozenset({"flaresolverr", "recyclarr"})


class PublicHostnameError(ValueError):
    """Invalid public hostname preference."""


def hostnames_path(app_settings: Settings | None = None) -> Path:
    return (app_settings or settings).config_dir / _FILE_NAME


def normalize_subdomain(value: str) -> str:
    label = (value or "").strip().lower().strip(".")
    label = re.sub(r"[^a-z0-9-]", "", label)
    return label


def validate_subdomain(value: str) -> str:
    label = normalize_subdomain(value)
    if not label or not _SUBDOMAIN_RE.match(label):
        raise PublicHostnameError(
            f"Invalid subdomain {value!r}. Use letters, digits, and hyphens "
            "(e.g. sonarr or watch)."
        )
    return label


def load_hostnames(app_settings: Settings | None = None) -> dict[str, dict[str, Any]]:
    path = hostnames_path(app_settings)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as err:
        logger.warning("Could not read %s: %s", path, err)
        return {}
    if not isinstance(data, dict):
        return {}
    clean: dict[str, dict[str, Any]] = {}
    for key, raw in data.items():
        name = str(key).strip().lower()
        if not name:
            continue
        if isinstance(raw, str):
            try:
                clean[name] = {"subdomain": validate_subdomain(raw), "enabled": True}
            except PublicHostnameError:
                continue
            continue
        if not isinstance(raw, dict):
            continue
        sub = normalize_subdomain(str(raw.get("subdomain") or name))
        if not sub:
            continue
        try:
            sub = validate_subdomain(sub)
        except PublicHostnameError:
            continue
        entry: dict[str, Any] = {
            "subdomain": sub,
            "enabled": bool(raw.get("enabled", True)),
        }
        last = str(raw.get("last_published") or "").strip().lower()
        if last:
            entry["last_published"] = last
        try:
            last_port = int(raw.get("last_published_port"))
        except (TypeError, ValueError):
            last_port = 0
        if last_port > 0:
            entry["last_published_port"] = last_port
        clean[name] = entry
    return clean


def save_hostnames(
    entries: dict[str, Any],
    *,
    app_settings: Settings | None = None,
    preserve_last_published: bool = True,
) -> dict[str, dict[str, Any]]:
    previous = load_hostnames(app_settings) if preserve_last_published else {}
    clean: dict[str, dict[str, Any]] = {}
    seen_subs: dict[str, str] = {}
    for key, raw in (entries or {}).items():
        name = str(key).strip().lower()
        if not name:
            continue
        if isinstance(raw, str):
            enabled = True
            sub_raw = raw
            last_published = ""
        elif isinstance(raw, dict):
            enabled = bool(raw.get("enabled", True))
            sub_raw = str(raw.get("subdomain") or name)
            last_published = str(raw.get("last_published") or "").strip().lower()
        else:
            continue
        sub = validate_subdomain(sub_raw)
        other = seen_subs.get(sub)
        if other and other != name:
            raise PublicHostnameError(f"Subdomain {sub!r} is already used by {other}.")
        seen_subs[sub] = name
        prev_entry = previous.get(name) or {}
        if not last_published and preserve_last_published:
            last_published = str(prev_entry.get("last_published") or "").strip().lower()
        last_port = 0
        if isinstance(raw, dict):
            try:
                last_port = int(raw.get("last_published_port") or 0)
            except (TypeError, ValueError):
                last_port = 0
        if not last_port and preserve_last_published:
            try:
                last_port = int(prev_entry.get("last_published_port") or 0)
            except (TypeError, ValueError):
                last_port = 0
        entry: dict[str, Any] = {"subdomain": sub, "enabled": enabled}
        if last_published:
            entry["last_published"] = last_published
        if last_port > 0:
            entry["last_published_port"] = last_port
        clean[name] = entry

    cfg = app_settings or settings
    cfg.config_dir.mkdir(parents=True, exist_ok=True)
    path = hostnames_path(cfg)
    path.write_text(json.dumps(clean, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return clean


def mark_published(
    published: dict[str, str],
    *,
    cleared: list[str] | None = None,
    ports: dict[str, int] | None = None,
    app_settings: Settings | None = None,
) -> dict[str, dict[str, Any]]:
    """Record hostnames last pushed to Cloudflare (or clear after unpublish)."""
    data = load_hostnames(app_settings)
    port_map = {str(k).strip().lower(): int(v) for k, v in (ports or {}).items()}
    for name, hostname in (published or {}).items():
        key = str(name).strip().lower()
        host = str(hostname or "").strip().lower()
        if not key or not host:
            continue
        entry = dict(data.get(key) or {"subdomain": key, "enabled": True})
        entry["last_published"] = host
        if key in port_map and port_map[key] > 0:
            entry["last_published_port"] = port_map[key]
        data[key] = entry
    for name in cleared or []:
        key = str(name).strip().lower()
        if key in data:
            data[key].pop("last_published", None)
            data[key].pop("last_published_port", None)
    return save_hostnames(data, app_settings=app_settings, preserve_last_published=False)


def subdomain_for(app_name: str, *, app_settings: Settings | None = None) -> str | None:
    """Return custom subdomain when the app is enabled in the map; else None."""
    name = (app_name or "").strip().lower()
    entry = load_hostnames(app_settings).get(name)
    if not entry or not entry.get("enabled"):
        return None
    sub = normalize_subdomain(str(entry.get("subdomain") or ""))
    return sub or None


def catalog_public_apps() -> list[dict[str, Any]]:
    """Apps (plus manager) that can get a public hostname."""
    from applications.catalog import ApplicationCatalog

    cat = ApplicationCatalog(app_settings=settings)
    rows: list[dict[str, Any]] = [
        {
            "name": MANAGER_KEY,
            "display_name": "AIO Media Manager",
            "port": int(settings.api_port),
            "installed": True,
            "default_subdomain": "media",
        }
    ]
    for plugin in cat.visible_plugins():
        if plugin.name in _SKIP_PUBLIC_UI:
            continue
        if not plugin.port:
            continue
        rows.append(
            {
                "name": plugin.name,
                "display_name": plugin.manifest.display_name,
                "port": int(plugin.port),
                "installed": bool(plugin.is_installed()),
                "default_subdomain": plugin.name,
            }
        )
    return rows
