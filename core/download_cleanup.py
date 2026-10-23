"""Remove downloads that will not finish (stalled, files missing) from Home.

A download Sonarr or Radarr tracks goes through them: removed from the client, blocklisted so
that release is not grabbed again, and searched for anew. Anything else is deleted from its
download client together with its partial files.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)


def _arr_queue_remove(name: str, wanted: set[str]) -> set[str]:
    """Remove queue entries whose download id is wanted; returns the ids it handled."""
    from applications.catalog import ApplicationCatalog
    from core.integrations.credentials import get_application_api_key

    catalog = ApplicationCatalog()
    if not catalog.has(name) or not catalog.get(name).is_installed():
        return set()
    plugin = catalog.get(name)
    base = f"http://127.0.0.1:{plugin.port}/api/v3"
    headers = {"X-Api-Key": get_application_api_key(name, plugin.config_dir) or ""}
    try:
        records = requests.get(f"{base}/queue", headers=headers, params={"page": 1, "pageSize": 1000}, timeout=20).json()
        rows = [row for row in records.get("records", []) if str(row.get("downloadId") or "").lower() in wanted]
        if rows:
            requests.delete(
                f"{base}/queue/bulk",
                headers=headers,
                params={"removeFromClient": "true", "blocklist": "true", "skipRedownload": "false"},
                json={"ids": [row["id"] for row in rows]},
                timeout=60,
            ).raise_for_status()
    except (requests.RequestException, ValueError, AttributeError) as exc:
        logger.warning("Could not remove downloads through %s: %s", name, exc)
        return set()
    return {str(row.get("downloadId") or "").lower() for row in rows}


def _client_remove(source: str, ids: list[str]) -> bool:
    from core.downloads_pause import _clients

    client = _clients().get(source)
    if client is None or not ids:
        return False
    if source == "qbittorrent":
        resp = client.session.post(f"{client.base_url}/torrents/delete", data={"hashes": "|".join(ids), "deleteFiles": "true"}, timeout=20)
        return resp.status_code == 200
    if source == "sabnzbd":
        return client._request("queue", {"name": "delete", "value": ",".join(ids), "del_files": 1}).get("status") is not False
    return bool(client._call("editqueue", ["GroupFinalDelete", "", [int(i) for i in ids if i.isdigit()]]))


def remove_downloads(items: list[dict[str, Any]]) -> dict[str, Any]:
    # Sonarr/Radarr write qBittorrent hashes in upper case, so match case-insensitively but keep
    # the original id for the client: SABnzbd ids (SABnzbd_nzo_…) are case-sensitive.
    wanted = {
        str(item["download_id"]).lower(): (str(item.get("source") or ""), str(item["download_id"]))
        for item in items
        if item.get("download_id")
    }
    handled: set[str] = set()
    for name in ("sonarr", "radarr"):
        handled |= _arr_queue_remove(name, set(wanted) - handled)
    direct: dict[str, list[str]] = {}
    for key, (source, download_id) in wanted.items():
        if key not in handled:
            direct.setdefault(source, []).append(download_id)
    removed_direct = sum(len(ids) for source, ids in direct.items() if _client_remove(source, ids))
    logger.info("Removed %s stuck download(s): %s via Sonarr/Radarr, %s directly.", len(wanted), len(handled), removed_direct)
    return {"requested": len(wanted), "searched_again": len(handled), "removed_from_client": removed_direct}
