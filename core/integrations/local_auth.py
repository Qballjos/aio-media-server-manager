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
        from core.integrations.qbittorrent import apply_qbittorrent_webui_login

        ok = apply_qbittorrent_webui_login(
            config_dir_for("qbittorrent"),
            port_for("qbittorrent", 8081),
        )
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

        client = JellyfinClient(
            port=port_for("jellyfin", 8096),
            api_key=api_key_for("jellyfin"),
            config_dir=config_dir_for("jellyfin"),
        )
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


def bazarr_password_hash(password: str) -> str:
    """Bazarr compares login against MD5 hex of the password, not SHA-256."""
    return hashlib.md5(password.encode("utf-8")).hexdigest()


def bazarr_config_yaml(config_dir: Path) -> Path:
    return Path(config_dir) / "config" / "config.yaml"


def patch_bazarr_auth_yaml(config_path: Path, username: str, password: str) -> bool:
    hashed = bazarr_password_hash(password)
    path = Path(config_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    updated = _rewrite_bazarr_auth_block(text, username, hashed)
    if updated != text:
        path.write_text(updated, encoding="utf-8")
        return True
    return False


def _rewrite_bazarr_auth_block(text: str, username: str, hashed: str) -> str:
    user_line = f"  username: {json.dumps(username)}"
    pass_line = f"  password: {hashed}"
    type_line = "  type: form"
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if re.match(r"^auth:\s*$", line)), None)
    if start is None:
        extra = ["auth:", type_line, user_line, pass_line]
        if not text.strip():
            return "---\n" + "\n".join(extra) + "\n"
        body = text if text.endswith("\n") else text + "\n"
        return body + "\n".join(extra) + "\n"

    end = len(lines)
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if line and not line[0].isspace() and not line.startswith("#"):
            end = index
            break
    block = lines[start:end]
    replaced = {"username": False, "password": False, "type": False}
    new_block = [block[0]]
    for line in block[1:]:
        stripped = line.lstrip(" \t")
        if stripped.startswith("username:"):
            new_block.append(user_line)
            replaced["username"] = True
        elif stripped.startswith("password:"):
            new_block.append(pass_line)
            replaced["password"] = True
        elif stripped.startswith("type:"):
            new_block.append(type_line)
            replaced["type"] = True
        else:
            new_block.append(line)
    if not replaced["type"]:
        new_block.insert(1, type_line)
    if not replaced["username"]:
        new_block.append(user_line)
    if not replaced["password"]:
        new_block.append(pass_line)
    result = "\n".join(lines[:start] + new_block + lines[end:])
    if text.endswith("\n") or not result.endswith("\n"):
        result = result.rstrip("\n") + "\n"
    return result


def restart_bazarr_if_running() -> None:
    try:
        from core.supervisor import ProcessSupervisor

        supervisor = ProcessSupervisor.get()
        if supervisor.status("bazarr").value != "running":
            return
        supervisor.run_coroutine_sync(supervisor.restart("bazarr"), timeout=90.0)
    except Exception as exc:
        logger.debug("Bazarr restart after login seed skipped: %s", exc)


def _step(target: str, action: str, ok: bool, detail: str) -> dict[str, Any]:
    return {
        "target": target,
        "action": action,
        "status": "success" if ok else "warning",
        "detail": detail,
    }
