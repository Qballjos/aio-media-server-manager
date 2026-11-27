"""Validate and check a connection to a local arr-mcp server."""

from __future__ import annotations

import asyncio
import json
from ipaddress import ip_address, ip_network
from urllib.parse import urlsplit

import httpx

_NETWORKS = tuple(ip_network(value) for value in (
    "127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "::1/128", "fc00::/7",
))
_MAX_BYTES = 8192


class ArrMcpError(ValueError):
    """The local arr-mcp connection could not be configured or verified."""


def local_endpoint(value: str, *, mcp: bool = True) -> str:
    """Accept an exact local endpoint without DNS, redirects or embedded credentials."""
    if any(character.isspace() or not character.isprintable() for character in value):
        raise ArrMcpError("Enter a local HTTP or HTTPS address.")
    try:
        url = urlsplit(value)
        host = ip_address(url.hostname or "")
        if (
            url.scheme not in ("http", "https") or (mcp and url.path != "/mcp")
            or url.username is not None or url.password is not None
            or url.query or url.fragment or "?" in value or "#" in value or "%" in url.netloc
            or not any(host in network for network in _NETWORKS)
            or (url.port is not None and url.port == 0)
        ):
            raise ValueError
    except ValueError:
        raise ArrMcpError(
            "Enter a local IP address ending in /mcp." if mcp else "Enter a local chat URL using an IP address."
        ) from None
    return value


async def check_connection(endpoint: str, token: str) -> None:
    endpoint = local_endpoint(endpoint)
    try:
        async with (
            asyncio.timeout(5),
            httpx.AsyncClient(timeout=4, follow_redirects=False, trust_env=False) as client,
        ):
            async with client.stream(
                "POST", endpoint,
                headers={
                    "Authorization": f"Bearer {token}", "Accept": "application/json", "Accept-Encoding": "identity",
                },
                json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
            ) as response:
                response.raise_for_status()
                if response.headers.get("content-encoding", "identity").lower() != "identity":
                    raise ValueError
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(body) + len(chunk) > _MAX_BYTES:
                        raise ValueError
                    body.extend(chunk)
        result = json.loads(body)
        if (
            result.get("jsonrpc") != "2.0" or result.get("id") != 1
            or "error" in result or not isinstance(result.get("result"), dict)
        ):
            raise ValueError
    except (httpx.HTTPError, ValueError, TimeoutError, AttributeError, RecursionError):
        raise ArrMcpError("Could not verify the local arr-mcp connection.") from None
