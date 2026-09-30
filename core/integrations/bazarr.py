"""Bazarr API client — pair subtitle manager with Sonarr and Radarr."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

_DEFAULT_PORTS = {"sonarr": 8989, "radarr": 7878}


class BazarrClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 6767, api_key: Optional[str] = None):
        self.base_url = f"http://{host}:{port}/api"
        self.api_key = api_key

    def _headers(self, *, form: bool = False) -> dict[str, str]:
        headers: dict[str, str] = {}
        if not form:
            headers["Content-Type"] = "application/json"
        if self.api_key:
            headers["X-API-KEY"] = self.api_key
        return headers

    def pair_sonarr(self, sonarr_url: str, api_key: str, config_dir=None) -> bool:
        ok, _api_ok = self._pair("sonarr", sonarr_url, api_key, config_dir)
        return ok

    def pair_radarr(self, radarr_url: str, api_key: str, config_dir=None) -> bool:
        ok, _api_ok = self._pair("radarr", radarr_url, api_key, config_dir)
        return ok

    def pair_libraries(
        self,
        *,
        sonarr_url: str = "",
        sonarr_key: str = "",
        radarr_url: str = "",
        radarr_key: str = "",
        config_dir=None,
    ) -> bool:
        results: list[bool] = []
        if sonarr_url and sonarr_key:
            ok, _api_ok = self._pair("sonarr", sonarr_url, sonarr_key, config_dir)
            results.append(ok)
        if radarr_url and radarr_key:
            ok, _api_ok = self._pair("radarr", radarr_url, radarr_key, config_dir)
            results.append(ok)
        return all(results) if results else False

    def _pair(
        self,
        kind: str,
        url: str,
        api_key: str,
        config_dir=None,
    ) -> tuple[bool, bool]:
        host, port, ssl = _split_arr_url(url, kind)
        form = {
            f"settings-{kind}-ip": host,
            f"settings-{kind}-port": str(port),
            f"settings-{kind}-apikey": api_key,
            f"settings-{kind}-base_url": "/",
            f"settings-{kind}-ssl": "true" if ssl else "false",
            f"settings-general-use_{kind}": "true",
        }
        api_ok = False
        try:
            resp = requests.post(
                f"{self.base_url}/system/settings",
                headers=self._headers(form=True),
                data=form,
                timeout=8.0,
            )
            api_ok = resp.status_code in (200, 201, 204)
            if not api_ok:
                logger.debug(
                    "Bazarr %s settings POST returned %s: %s",
                    kind,
                    resp.status_code,
                    (resp.text or "")[:200],
                )
        except Exception as exc:
            logger.debug("Bazarr pair %s via settings API failed: %s", kind, exc)

        yaml_ok = False
        if config_dir is not None:
            yaml_ok = patch_bazarr_arr_yaml(
                Path(config_dir), kind, host, port, api_key, ssl=ssl
            )
        ok = api_ok or yaml_ok
        if ok:
            logger.info("Bazarr paired with %s at %s:%s", kind, host, port)
        return ok, api_ok

    def _reload(self) -> None:
        from core.integrations.local_auth import restart_bazarr_if_running

        restart_bazarr_if_running()

    def set_ui_auth(self, username: str, password: str, config_dir) -> bool:
        from core.integrations.local_auth import bazarr_config_yaml, patch_bazarr_auth_yaml, restart_bazarr_if_running

        yaml_changed = patch_bazarr_auth_yaml(bazarr_config_yaml(Path(config_dir)), username, password)
        payload = {"auth": {"type": "form", "username": username, "password": password}}
        endpoints = (f"{self.base_url}/system/settings", f"{self.base_url}/settings")
        for endpoint in endpoints:
            try:
                resp = requests.post(endpoint, headers=self._headers(), json=payload, timeout=5.0)
                if resp.status_code in (200, 201, 204):
                    return True
            except Exception as exc:
                logger.debug("Bazarr set_ui_auth via %s failed: %s", endpoint, exc)
        if yaml_changed:
            restart_bazarr_if_running()
        return yaml_changed or bazarr_config_yaml(Path(config_dir)).is_file()


def _split_arr_url(url: str, kind: str) -> tuple[str, int, bool]:
    parsed = urlparse(url if "://" in url else f"http://{url}")
    host = parsed.hostname or "127.0.0.1"
    ssl = parsed.scheme == "https"
    port = parsed.port or (443 if ssl else _DEFAULT_PORTS.get(kind, 80))
    return host, int(port), ssl


def patch_bazarr_arr_yaml(
    config_dir: Path,
    kind: str,
    host: str,
    port: int,
    api_key: str,
    *,
    ssl: bool = False,
) -> bool:
    from core.integrations.local_auth import bazarr_config_yaml

    path = bazarr_config_yaml(Path(config_dir))
    path.parent.mkdir(parents=True, exist_ok=True)
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    updated = _rewrite_bazarr_arr_block(text, kind, host, port, api_key, ssl)
    flag = f"use_{kind}"
    flag_line = f"  {flag}: true"
    if re.search(rf"(?m)^  {re.escape(flag)}:\s*.*$", updated):
        updated = re.sub(rf"(?m)^  {re.escape(flag)}:\s*.*$", flag_line, updated, count=1)
    else:
        updated = _insert_general_flag(updated, flag_line)
    if updated != text:
        path.write_text(updated, encoding="utf-8")
    return True


def _insert_general_flag(text: str, flag_line: str) -> str:
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if re.match(r"^general:\s*$", line)), None)
    if start is None:
        extra = ["general:", flag_line]
        body = text if text.endswith("\n") or not text.strip() else text + "\n"
        if not text.strip():
            return "---\n" + "\n".join(extra) + "\n"
        return body + "\n".join(extra) + "\n"
    lines.insert(start + 1, flag_line)
    result = "\n".join(lines)
    if text.endswith("\n") or not result.endswith("\n"):
        result = result.rstrip("\n") + "\n"
    return result


def _rewrite_bazarr_arr_block(
    text: str,
    kind: str,
    host: str,
    port: int,
    api_key: str,
    ssl: bool,
) -> str:
    values = {
        "ip": host,
        "port": str(port),
        "apikey": api_key,
        "ssl": "true" if ssl else "false",
        "base_url": "/",
    }
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if re.match(rf"^{kind}:\s*$", line)), None)
    if start is None:
        extra = [f"{kind}:"] + [f"  {key}: {value}" for key, value in values.items()]
        body = text if text.endswith("\n") or not text else text + "\n"
        if not text.strip():
            return "---\n" + "\n".join(extra) + "\n"
        return body + "\n".join(extra) + "\n"

    end = len(lines)
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if line and not line[0].isspace() and not line.startswith("#"):
            end = index
            break

    block = lines[start:end]
    replaced = {key: False for key in values}
    new_block = [block[0]]
    for line in block[1:]:
        stripped = line.lstrip(" \t")
        key = stripped.split(":", 1)[0] if ":" in stripped else ""
        if key in values:
            new_block.append(f"  {key}: {values[key]}")
            replaced[key] = True
        else:
            new_block.append(line)
    for key, value in values.items():
        if not replaced[key]:
            new_block.append(f"  {key}: {value}")
    result = "\n".join(lines[:start] + new_block + lines[end:])
    if text.endswith("\n") or not result.endswith("\n"):
        result = result.rstrip("\n") + "\n"
    return result
