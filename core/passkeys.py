"""WebAuthn ceremonies for the manager's local administrator."""

from __future__ import annotations

import ipaddress
import time
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

from webauthn import base64url_to_bytes
from webauthn.helpers import bytes_to_base64url

CHALLENGE_TTL = 180
MAX_PENDING = 128
Purpose = Literal["register", "login"]


def relying_party(origin: str, host: str) -> str | None:
    """Match the browser origin to the public Host, including behind TLS proxies."""
    try:
        url = urlsplit(origin)
        hostname = url.hostname
        port = url.port
    except ValueError:
        return None
    if not hostname or url.username is not None or url.password is not None:
        return None
    if url.scheme != "https" and not (url.scheme == "http" and hostname == "localhost"):
        return None
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        return None

    authority = hostname if port is None else f"{hostname}:{port}"
    default_port = 443 if url.scheme == "https" else 80
    if origin != f"{url.scheme}://{authority}":
        return None
    if host.lower() not in {authority, f"{hostname}:{default_port}" if port is None else authority}:
        return None
    return hostname


@dataclass(frozen=True)
class Challenge:
    expires: float
    purpose: Purpose
    origin: str
    binding: str


class PasskeyChallenges:
    """Short-lived, single-use ceremonies in the appliance API process."""

    def __init__(self) -> None:
        self._pending: dict[str, Challenge] = {}

    def add(self, challenge: bytes, purpose: Purpose, origin: str, binding: str) -> None:
        now = time.monotonic()
        self._pending = {key: value for key, value in self._pending.items() if value.expires > now}
        if len(self._pending) >= MAX_PENDING:
            del self._pending[next(iter(self._pending))]
        self._pending[bytes_to_base64url(challenge)] = Challenge(now + CHALLENGE_TTL, purpose, origin, binding)

    def take(self, key: str, purpose: Purpose, origin: str, binding: str) -> bytes | None:
        pending = self._pending.get(key)
        if not pending or pending.purpose != purpose or pending.origin != origin or pending.binding != binding:
            return None
        del self._pending[key]
        return base64url_to_bytes(key) if pending.expires > time.monotonic() else None
