"""Generic Servarr (*Arr) API helpers for root folders and download clients."""

from __future__ import annotations

import logging
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

_PROTOCOL = {"Sabnzbd": "usenet", "Nzbget": "usenet", "QBittorrent": "torrent"}


def post_servarr_download_client(
    base_url: str,
    headers: dict[str, str],
    *,
    name: str,
    implementation: str,
    config_contract: str,
    fields: list[dict[str, Any]],
    label: str,
) -> bool:
    """Create a download client from schema when possible, skipping the live test."""
    payload = _download_client_payload(
        base_url,
        headers,
        name=name,
        implementation=implementation,
        config_contract=config_contract,
        fields=fields,
    )
    try:
        resp = requests.post(
            f"{base_url}/downloadclient",
            headers=headers,
            params={"forceSave": "true"},
            json=payload,
            timeout=15.0,
        )
        if resp.status_code in (200, 201):
            return True
        logger.warning("%s add %s failed (%s): %s", label, implementation, resp.status_code, resp.text[:500])
        return False
    except Exception as exc:
        logger.debug("%s add %s error: %s", label, implementation, exc)
        return False


def _download_client_payload(
    base_url: str,
    headers: dict[str, str],
    *,
    name: str,
    implementation: str,
    config_contract: str,
    fields: list[dict[str, Any]],
) -> dict[str, Any]:
    template = _schema_template(base_url, headers, implementation)
    protocol = _PROTOCOL.get(implementation, "torrent")
    if template:
        merged = dict(template)
        merged.pop("presets", None)
        merged["id"] = 0
        merged["enable"] = True
        merged["name"] = name
        merged["implementation"] = implementation
        merged["configContract"] = config_contract
        merged["protocol"] = template.get("protocol") or protocol
        merged["tags"] = template.get("tags") or []
        merged["priority"] = template.get("priority") or 1
        merged["fields"] = _overlay_fields(template.get("fields") or [], fields)
        return merged
    return {
        "enable": True,
        "protocol": protocol,
        "priority": 1,
        "removeCompletedDownloads": True,
        "removeFailedDownloads": True,
        "name": name,
        "implementation": implementation,
        "configContract": config_contract,
        "tags": [],
        "fields": fields,
    }


def _schema_template(base_url: str, headers: dict[str, str], implementation: str) -> dict[str, Any] | None:
    try:
        resp = requests.get(f"{base_url}/downloadclient/schema", headers=headers, timeout=8.0)
        if resp.status_code != 200:
            return None
        rows = resp.json()
        if not isinstance(rows, list):
            return None
        for row in rows:
            if isinstance(row, dict) and row.get("implementation") == implementation:
                return row
    except Exception as exc:
        logger.debug("download client schema error: %s", exc)
    return None


def _overlay_fields(schema_fields: list[Any], overrides: list[dict[str, Any]]) -> list[dict[str, Any]]:
    values = {item.get("name"): item.get("value") for item in overrides if item.get("name")}
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for field in schema_fields:
        if not isinstance(field, dict):
            continue
        item = dict(field)
        field_name = str(item.get("name") or "")
        if field_name in values:
            item["value"] = values[field_name]
            seen.add(field_name)
        merged.append(item)
    for item in overrides:
        field_name = str(item.get("name") or "")
        if field_name and field_name not in seen:
            merged.append(dict(item))
    return merged


class ArrAppClient:
    """Minimal *Arr v1 client used for Lidarr wiring."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8686,
        api_key: Optional[str] = None,
        *,
        api_prefix: str = "/api/v1",
        category_field: str = "musicCategory",
        label: str = "Arr",
    ) -> None:
        self.base_url = f"http://{host}:{port}{api_prefix}"
        self.api_key = api_key
        self.category_field = category_field
        self.label = label

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-Api-Key"] = self.api_key
        return headers

    def get_root_folders(self) -> list[dict[str, Any]]:
        try:
            resp = requests.get(f"{self.base_url}/rootfolder", headers=self._headers(), timeout=5.0)
            if resp.status_code == 200:
                return resp.json()
        except Exception as exc:
            logger.debug("%s get_root_folders error: %s", self.label, exc)
        return []

    def add_root_folder(self, path: str) -> bool:
        folders = self.get_root_folders()
        if any(str(item.get("path", "")).rstrip("/") == path.rstrip("/") for item in folders):
            logger.info("%s root folder '%s' already configured.", self.label, path)
            return True
        try:
            resp = requests.post(
                f"{self.base_url}/rootfolder",
                headers=self._headers(),
                json={"path": path},
                timeout=5.0,
            )
            return resp.status_code in (200, 201)
        except Exception as exc:
            logger.debug("%s add_root_folder error: %s", self.label, exc)
            return False

    def get_download_clients(self) -> list[dict[str, Any]]:
        try:
            resp = requests.get(f"{self.base_url}/downloadclient", headers=self._headers(), timeout=5.0)
            if resp.status_code == 200:
                return resp.json()
        except Exception as exc:
            logger.debug("%s get_download_clients error: %s", self.label, exc)
        return []

    def add_sabnzbd_client(
        self,
        host: str = "127.0.0.1",
        port: int = 8085,
        api_key: str = "",
        category: str = "",
    ) -> bool:
        if any(item.get("implementation") == "Sabnzbd" for item in self.get_download_clients()):
            return True
        return self._post_download_client(
            "SABnzbd (AMM)",
            "Sabnzbd",
            "SabnzbdSettings",
            [
                {"name": "host", "value": host},
                {"name": "port", "value": port},
                {"name": "apiKey", "value": api_key},
                {"name": self.category_field, "value": category},
                {"name": "useSsl", "value": False},
            ],
        )

    def add_nzbget_client(
        self,
        host: str = "127.0.0.1",
        port: int = 6789,
        username: str = "nzbget",
        password: str = "tegbzn6789",
        category: str = "",
    ) -> bool:
        if any(item.get("implementation") == "Nzbget" for item in self.get_download_clients()):
            return True
        return self._post_download_client(
            "NZBGet (AMM)",
            "Nzbget",
            "NzbgetSettings",
            [
                {"name": "host", "value": host},
                {"name": "port", "value": port},
                {"name": "username", "value": username},
                {"name": "password", "value": password},
                {"name": self.category_field, "value": category},
                {"name": "useSsl", "value": False},
            ],
        )

    def add_qbittorrent_client(
        self,
        host: str = "127.0.0.1",
        port: int = 8081,
        username: str = "admin",
        password: str = "adminadmin",
        category: str = "",
    ) -> bool:
        if any(item.get("implementation") == "QBittorrent" for item in self.get_download_clients()):
            return True
        return self._post_download_client(
            "qBittorrent (AMM)",
            "QBittorrent",
            "QBittorrentSettings",
            [
                {"name": "host", "value": host},
                {"name": "port", "value": port},
                {"name": "username", "value": username},
                {"name": "password", "value": password},
                {"name": self.category_field, "value": category},
                {"name": "useSsl", "value": False},
            ],
        )

    def _post_download_client(
        self,
        name: str,
        implementation: str,
        config_contract: str,
        fields: list[dict[str, Any]],
    ) -> bool:
        return post_servarr_download_client(
            self.base_url,
            self._headers(),
            name=name,
            implementation=implementation,
            config_contract=config_contract,
            fields=fields,
            label=self.label,
        )
