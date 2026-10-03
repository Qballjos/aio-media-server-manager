"""Write qBittorrent.conf defaults used by the process launcher."""

from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path

_WEBUI_LOCAL_DEFAULTS = {
    "WebUI\\LocalHostAuth": "false",
    "WebUI\\AuthSubnetWhitelistEnabled": "true",
    "WebUI\\AuthSubnetWhitelist": "127.0.0.0/8, ::1, 10.200.200.0/24, 172.16.0.0/12",
    "WebUI\\CSRFProtection": "false",
    "WebUI\\HostHeaderValidation": "false",
    "WebUI\\BannedIPs": "",
}

# Appliance defaults: VPN-safe, high-throughput, leave seed time/ratio to *Arr.
_PREFERENCES_CLIENT_DEFAULTS = {
    "Connection\\UPnP": "false",
    "Connection\\PortRangeMin": "6881",
    # Never listen/announce on IPv6 — house IPv6 is a common VPN bypass.
    "Connection\\InterfaceListenIPv6": "false",
    "Connection\\GlobalDLLimit": "-1",
    "Connection\\GlobalUPLimit": "-1",
    "Downloads\\PreAllocation": "true",
    "Downloads\\UseIncompleteExtension": "true",
    "Queueing\\QueueingEnabled": "false",
    # DHT/PeX are fine once traffic is bound to wg; LSD finds LAN peers (leak risk).
    "Bittorrent\\DHT": "true",
    "Bittorrent\\PeX": "true",
    "Bittorrent\\LSD": "false",
    "Bittorrent\\Encryption": "0",
    "Bittorrent\\MaxRatio": "-1",
    "Advanced\\AnonymousMode": "false",
    "Advanced\\AnnounceToAllTrackers": "true",
    "Advanced\\osCache": "true",
    "Advanced\\listenOnIPv6Address": "false",
}

_BITTORRENT_SESSION_DEFAULTS = {
    "Session\\AnonymousMode": "false",
    "Session\\DHTEnabled": "true",
    "Session\\PeXEnabled": "true",
    "Session\\LSDEnabled": "false",
    "Session\\Encryption": "0",
    "Session\\MaxConnections": "800",
    "Session\\MaxConnectionsPerTorrent": "200",
    "Session\\MaxUploads": "100",
    "Session\\MaxUploadsPerTorrent": "8",
    "Session\\GlobalMaxRatio": "-1",
    "Session\\GlobalMaxSeedingMinutes": "-1",
    "Session\\GlobalMaxInactiveSeedingMinutes": "-1",
    "Session\\MaxRatioAction": "0",
    "Session\\QueueingEnabled": "false",
    "Session\\Port": "6881",
    "Session\\UPnP": "false",
    "Session\\Preallocation": "true",
    "Session\\MultiConnectionsPerIp": "true",
    "Session\\IgnoreSlowTorrentsForQueueing": "true",
}


def ensure_vpn_network_interface(profile_dir: Path, iface: str | None) -> None:
    """Bind qBittorrent's BitTorrent sockets to the VPN interface (or clear the bind)."""
    name = (iface or "").strip()
    session = {
        "Session\\Interface": name,
        "Session\\InterfaceName": name,
        "Session\\InterfaceAddress": "",
    }
    preferences = {
        "Connection\\Interface": name,
        "Connection\\InterfaceName": name,
        "Connection\\InterfaceAddress": "",
        "Connection\\InterfaceListenIPv6": "false",
        "Advanced\\listenOnIPv6Address": "false",
        "Advanced\\networkInterface": name,
        "Advanced\\networkInterfaceName": name,
    }
    for conf in qbit_conf_paths(profile_dir):
        conf.parent.mkdir(parents=True, exist_ok=True)
        text = conf.read_text(encoding="utf-8") if conf.is_file() else ""
        lines = text.splitlines()
        lines = _upsert_ini_section(lines, "[BitTorrent]", session)
        lines = _upsert_ini_section(lines, "[Preferences]", preferences)
        conf.write_text("\n".join(lines) + "\n", encoding="utf-8")


def qbit_conf_paths(profile_dir: Path) -> tuple[Path, Path]:
    root = Path(profile_dir)
    return (
        root / "qBittorrent" / "qBittorrent.conf",
        root / "qBittorrent" / "config" / "qBittorrent.conf",
    )


def _ini_scalar(value: str) -> str:
    """Quote INI values that Qt would otherwise truncate (spaces, #, ;)."""
    text = str(value)
    if any(ch in text for ch in ' \t#;="'):
        return '"' + text.replace("\\", "/").replace('"', r"\"") + '"'
    return text


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
    alternative_ui_root: Path | None = None,
) -> Path:
    """Let *Arr and AMM talk to the WebUI, and persist LAN login when credentials exist."""
    written = None
    for conf in qbit_conf_paths(profile_dir):
        written = _write_webui_conf(
            conf,
            username=username,
            password=password,
            alternative_ui_root=alternative_ui_root,
        )
    return written or qbit_conf_paths(profile_dir)[0]


def _upsert_ini_section(lines: list[str], section_header: str, extras: dict[str, str]) -> list[str]:
    found = {key: False for key in extras}
    rewritten: list[str] = []
    in_section = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_section = stripped == section_header
            rewritten.append(line)
            continue
        matched = False
        if in_section:
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
        if not any(item.strip() == section_header for item in rewritten):
            rewritten.append(section_header)
        insert_at = next(i for i, item in enumerate(rewritten) if item.strip() == section_header) + 1
        rewritten[insert_at:insert_at] = [f"{key}={extras[key]}" for key in missing]
    return rewritten


def _write_webui_conf(
    conf: Path,
    *,
    username: str,
    password: str,
    alternative_ui_root: Path | None = None,
) -> Path:
    conf.parent.mkdir(parents=True, exist_ok=True)
    text = conf.read_text(encoding="utf-8") if conf.is_file() else ""
    extras: dict[str, str] = dict(_WEBUI_LOCAL_DEFAULTS)
    extras.update(_PREFERENCES_CLIENT_DEFAULTS)
    user = (username or "").strip()
    secret = password or ""
    if user and secret:
        extras["WebUI\\Username"] = user
        extras["WebUI\\Password_PBKDF2"] = qbittorrent_pbkdf2(secret)
    if alternative_ui_root is not None:
        root = Path(alternative_ui_root).expanduser()
        try:
            root = root.resolve()
        except OSError:
            root = root.absolute()
        extras["WebUI\\AlternativeUIEnabled"] = "true"
        extras["WebUI\\RootFolder"] = _ini_scalar(str(root))
    else:
        extras["WebUI\\AlternativeUIEnabled"] = "false"
        extras["WebUI\\RootFolder"] = ""
    lines = text.splitlines()
    lines = [line for line in lines if not line.strip().startswith("WebUI\\Password_ha1=")]
    lines = _upsert_ini_section(lines, "[Preferences]", extras)
    lines = _upsert_ini_section(lines, "[BitTorrent]", _BITTORRENT_SESSION_DEFAULTS)
    conf.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return conf
