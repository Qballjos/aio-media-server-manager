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
