"""Write qBittorrent.conf defaults used by the process launcher."""

from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path

_WEBUI_LOCAL_DEFAULTS = {
    "WebUI\\LocalHostAuth": "false",
    "WebUI\\AuthSubnetWhitelistEnabled": "true",
    "WebUI\\AuthSubnetWhitelist": "127.0.0.0/8, ::1",
    "WebUI\\CSRFProtection": "false",
    "WebUI\\HostHeaderValidation": "false",
    "WebUI\\BannedIPs": "",
}


def qbittorrent_pbkdf2(password: str, *, salt: bytes | None = None) -> str:
    """qBittorrent 4.2+ WebUI\\Password_PBKDF2 value (SHA-512, 100000 iterations)."""
    salt_bytes = salt if salt is not None else os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha512", password.encode("utf-8"), salt_bytes, 100000, dklen=64)
    encoded = base64.b64encode(salt_bytes).decode("ascii") + ":" + base64.b64encode(digest).decode("ascii")
    return f'"@ByteArray({encoded})"'


def ensure_webui_localhost_access(
    profile_dir: Path,
    *,
    username: str = "",
    password: str = "",
) -> Path:
    """Let *Arr on 127.0.0.1 talk to the WebUI, and persist LAN login when credentials exist."""
    conf = Path(profile_dir) / "qBittorrent" / "qBittorrent.conf"
    conf.parent.mkdir(parents=True, exist_ok=True)
    text = conf.read_text(encoding="utf-8") if conf.is_file() else ""
    lines = text.splitlines()
    extras: dict[str, str] = dict(_WEBUI_LOCAL_DEFAULTS)
    user = (username or "").strip()
    secret = password or ""
    if user and secret:
        extras["WebUI\\Username"] = user
        extras["WebUI\\Password_PBKDF2"] = qbittorrent_pbkdf2(secret)
    found = {key: False for key in extras}
    rewritten: list[str] = []
    for line in lines:
        stripped = line.strip()
        matched = False
        for key, value in extras.items():
            if stripped.startswith(f"{key}="):
                rewritten.append(f"{key}={value}")
                found[key] = True
                matched = True
                break
        if not matched:
            rewritten.append(line)
    missing = [key for key, seen in found.items() if not seen]
    if missing:
        if not any(item.strip() == "[Preferences]" for item in rewritten):
            rewritten.append("[Preferences]")
        insert_at = next(i for i, item in enumerate(rewritten) if item.strip() == "[Preferences]") + 1
        rewritten[insert_at:insert_at] = [f"{key}={extras[key]}" for key in missing]
    conf.write_text("\n".join(rewritten) + "\n", encoding="utf-8")
    return conf
