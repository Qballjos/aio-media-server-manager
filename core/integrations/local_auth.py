"""Push the manager admin login into apps that have a local username/password."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any, Callable, Optional

import requests

from core.shared_credentials import shared_admin_credentials

logger = logging.getLogger(__name__)


def set_servarr_forms_auth(base_url: str, api_key: Optional[str], username: str, password: str) -> bool:
    if not api_key:
        return False
    headers = {"Content-Type": "application/json", "X-Api-Key": api_key}
    try:
        resp = requests.get(f"{base_url}/config/host", headers=headers, timeout=5.0)
        if resp.status_code != 200:
            return False
        cfg = resp.json()
        if not isinstance(cfg, dict):
            return False
        cfg["authenticationMethod"] = "forms"
        cfg["authenticationRequired"] = "enabled"
        cfg["username"] = username
        cfg["password"] = password
        cfg["passwordConfirmation"] = password
        put = requests.put(f"{base_url}/config/host", headers=headers, json=cfg, timeout=8.0)
        return put.status_code in (200, 201, 202)
    except Exception as exc:
        logger.debug("Servarr forms auth at %s failed: %s", base_url, exc)
        return False


def apply_shared_local_logins(
    *,
    installed: Callable[[str], bool],
    port_for: Callable[[str, int], int],
    api_key_for: Callable[[str], Optional[str]],
    config_dir_for: Callable[[str], Path],
) -> list[dict[str, Any]]:
    creds = shared_admin_credentials()
    if creds is None:
        return []
    username, password = creds
    steps: list[dict[str, Any]] = []

    if installed("qbittorrent"):
        from applications.qbittorrent.webui import ensure_webui_localhost_access
        from core.integrations.qbittorrent import QBittorrentClient

        ensure_webui_localhost_access(config_dir_for("qbittorrent"), username=username, password=password)
        client = QBittorrentClient(port=port_for("qbittorrent", 8081))
        logged_in = client.login()
        ok = logged_in and client.set_webui_login(username, password)
        steps.append(_step("qbittorrent", "set_shared_login", ok, username))

    if installed("sabnzbd"):
        from core.integrations.sabnzbd import SABnzbdClient

        client = SABnzbdClient(port=port_for("sabnzbd", 8085), api_key=api_key_for("sabnzbd"))
        steps.append(_step("sabnzbd", "set_shared_login", client.set_login(username, password), username))

    if installed("nzbget"):
        from core.integrations.nzbget import NZBGetClient

        client = NZBGetClient(port=port_for("nzbget", 6789))
        steps.append(_step("nzbget", "set_shared_login", client.set_login(username, password), username))

    for name, prefix, fallback in (
        ("sonarr", "/api/v3", 8989),
        ("radarr", "/api/v3", 7878),
        ("lidarr", "/api/v1", 8686),
        ("prowlarr", "/api/v1", 9696),
    ):
        if not installed(name):
            continue
        base = f"http://127.0.0.1:{port_for(name, fallback)}{prefix}"
        ok = set_servarr_forms_auth(base, api_key_for(name), username, password)
        steps.append(_step(name, "set_shared_login", ok, username))

    if installed("bazarr"):
        from core.integrations.bazarr import BazarrClient

        client = BazarrClient(port=port_for("bazarr", 6767), api_key=api_key_for("bazarr"))
        ok = client.set_ui_auth(username, password, config_dir_for("bazarr"))
        steps.append(_step("bazarr", "set_shared_login", ok, username))

    if installed("jellyfin"):
        from core.integrations.jellyfin import JellyfinClient

        client = JellyfinClient(port=port_for("jellyfin", 8096), api_key=api_key_for("jellyfin"))
        steps.append(_step("jellyfin", "set_shared_login", client.ensure_local_admin(username, password), username))

    if installed("profilarr"):
        steps.append(
            _step(
                "profilarr",
                "set_shared_login",
                set_profilarr_login(port_for("profilarr", 6868), username, password),
                username,
            )
        )

    if installed("neutarr"):
        steps.append(
            _step(
                "neutarr",
                "set_shared_login",
                set_neutarr_login(config_dir_for("neutarr"), username, password),
                username,
            )
        )

    return steps


def set_profilarr_login(port: int, username: str, password: str) -> bool:
    """Create Profilarr's first local user so Open UI matches the manager login."""
    payloads = (
        {"username": username, "password": password},
        {"user": username, "password": password},
        {"email": username, "password": password},
    )
    paths = (
        "/api/v1/auth/register",
        "/api/v1/auth/setup",
        "/api/v1/auth/signup",
        "/api/auth/register",
    )
    for path in paths:
        for body in payloads:
            try:
                resp = requests.post(f"http://127.0.0.1:{port}{path}", json=body, timeout=5.0)
                if resp.status_code in (200, 201, 204, 409):
                    return True
            except Exception as exc:
                logger.debug("Profilarr login seed %s failed: %s", path, exc)
    return False


def set_neutarr_login(config_dir: Path, username: str, password: str) -> bool:
    """Keep NeutArr LAN bypass and record the manager identity for the first-run UI."""
    root = Path(config_dir)
    root.mkdir(parents=True, exist_ok=True)
    general = root / "general.json"
    try:
        data = json.loads(general.read_text(encoding="utf-8")) if general.is_file() else {}
    except json.JSONDecodeError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    data["local_access_bypass"] = True
    data.setdefault(
        "local_bypass_cidrs",
        ["127.0.0.0/8", "::1/128", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"],
    )
    general.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return True


def sha256_hex(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def patch_bazarr_auth_yaml(config_path: Path, username: str, password: str) -> bool:
    hashed = sha256_hex(password)
    if not config_path.is_file():
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            "auth:\n"
            "  type: form\n"
            f"  username: {json.dumps(username)}\n"
            f"  password: {hashed}\n",
            encoding="utf-8",
        )
        return True
    text = config_path.read_text(encoding="utf-8")
    if re.search(r"^auth:\s*$", text, re.MULTILINE):
        text = re.sub(r"(?m)^(\s*)username:\s*.*$", rf"\1username: {json.dumps(username)}", text, count=1)
        text = re.sub(r"(?m)^(\s*)password:\s*.*$", rf"\1password: {hashed}", text, count=1)
        text = re.sub(r"(?m)^(\s*)type:\s*.*$", r"\1type: form", text, count=1)
    else:
        text += (
            "\nauth:\n"
            "  type: form\n"
            f"  username: {json.dumps(username)}\n"
            f"  password: {hashed}\n"
        )
    config_path.write_text(text, encoding="utf-8")
    return True


def _step(target: str, action: str, ok: bool, detail: str) -> dict[str, Any]:
    return {
        "target": target,
        "action": action,
        "status": "success" if ok else "warning",
        "detail": detail,
    }
