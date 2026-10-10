"""Usenet news-server credentials collected during first-run."""

from __future__ import annotations

from typing import Any, Optional

from core.crypto import secret_store

USENET_HOST = "usenet_host"
USENET_PORT = "usenet_port"
USENET_SSL = "usenet_ssl"
USENET_USERNAME = "usenet_username"
USENET_PASSWORD = "usenet_password"
USENET_CONNECTIONS = "usenet_connections"


def save_usenet_server(
    *,
    host: str,
    port: int = 563,
    ssl: bool = True,
    username: str = "",
    password: str = "",
    connections: int = 8,
) -> None:
    host = (host or "").strip()
    if not host:
        return
    secret_store.save_secret(USENET_HOST, host)
    secret_store.save_secret(USENET_PORT, str(int(port) or 563))
    secret_store.save_secret(USENET_SSL, "1" if ssl else "0")
    secret_store.save_secret(USENET_USERNAME, (username or "").strip())
    if password:
        secret_store.save_secret(USENET_PASSWORD, password)
    secret_store.save_secret(USENET_CONNECTIONS, str(max(1, int(connections) or 8)))


def load_usenet_server() -> Optional[dict[str, Any]]:
    host = (secret_store.get_secret(USENET_HOST) or "").strip()
    if not host:
        return None
    try:
        port = int(secret_store.get_secret(USENET_PORT) or "563")
    except ValueError:
        port = 563
    try:
        connections = int(secret_store.get_secret(USENET_CONNECTIONS) or "8")
    except ValueError:
        connections = 8
    return {
        "host": host,
        "port": port,
        "ssl": secret_store.get_secret(USENET_SSL) != "0",
        "username": secret_store.get_secret(USENET_USERNAME) or "",
        "password": secret_store.get_secret(USENET_PASSWORD) or "",
        "connections": max(1, connections),
    }


def public_usenet_server() -> Optional[dict[str, Any]]:
    """The stored provider without its password, for the dashboard."""
    server = load_usenet_server()
    if not server:
        return None
    public = {key: value for key, value in server.items() if key != "password"}
    public["has_password"] = bool(server.get("password"))
    return public


def push_usenet_server(previous_host: str = "") -> dict[str, bool]:
    """Send the stored provider to every installed Usenet client; False where it is not running."""
    server = load_usenet_server()
    if not server:
        return {}
    from applications.catalog import ApplicationCatalog
    from core.integrations.credentials import get_application_api_key
    from core.supervisor import ProcessSupervisor

    catalog = ApplicationCatalog()
    supervisor = ProcessSupervisor.get()
    applied: dict[str, bool] = {}
    for name in ("sabnzbd", "nzbget"):
        if not catalog.has(name) or not catalog.get(name).is_installed():
            continue
        if supervisor.status(name).value != "running":
            applied[name] = False
            continue
        plugin = catalog.get(name)
        if name == "sabnzbd":
            from core.integrations.sabnzbd import SABnzbdClient

            client = SABnzbdClient(port=plugin.port, api_key=get_application_api_key("sabnzbd", plugin.config_dir))
            if previous_host and previous_host.lower() != server["host"].lower():
                # A new provider replaces the old one instead of running next to it.
                client.remove_news_server(previous_host)
            applied[name] = client.add_news_server(**server, update=True)
        else:
            from core.integrations.nzbget import NZBGetClient

            # NZBGet keeps one server slot (Server1), so writing it replaces the old one.
            applied[name] = NZBGetClient(port=plugin.port).add_news_server(**server)
    return applied
