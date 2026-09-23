"""Write qBittorrent.conf defaults used by the process launcher."""

from __future__ import annotations

from pathlib import Path

_WEBUI_LOCAL_DEFAULTS = {
    "WebUI\\LocalHostAuth": "false",
    "WebUI\\AuthSubnetWhitelistEnabled": "true",
    "WebUI\\AuthSubnetWhitelist": "127.0.0.0/8, ::1",
    "WebUI\\CSRFProtection": "false",
    "WebUI\\HostHeaderValidation": "false",
    "WebUI\\BannedIPs": "",
}


def ensure_webui_localhost_access(profile_dir: Path) -> Path:
    """Let *Arr on 127.0.0.1 talk to the WebUI without triggering a ban."""
    conf = Path(profile_dir) / "qBittorrent" / "qBittorrent.conf"
    conf.parent.mkdir(parents=True, exist_ok=True)
    text = conf.read_text(encoding="utf-8") if conf.is_file() else ""
    lines = text.splitlines()
    found = {key: False for key in _WEBUI_LOCAL_DEFAULTS}
    rewritten: list[str] = []
    for line in lines:
        stripped = line.strip()
        matched = False
        for key, value in _WEBUI_LOCAL_DEFAULTS.items():
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
        rewritten[insert_at:insert_at] = [f"{key}={_WEBUI_LOCAL_DEFAULTS[key]}" for key in missing]
    conf.write_text("\n".join(rewritten) + "\n", encoding="utf-8")
    return conf
