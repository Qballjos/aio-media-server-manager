"""Notifications: the manager's own events (apps, VPN, Cloudflare tunnel, updates, disk) sent to
Discord and e-mail.

Settings live in ``config/notifications.json``; the Discord webhook and the SMTP password live
in the encrypted secret store. A loop compares the appliance state every minute and sends a
message when something changes (an app starts crash-looping, the VPN drops, a disk fills up,
an update appears), and again when it recovers.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import smtplib
import ssl
import time
from email.message import EmailMessage
from pathlib import Path
from typing import Any

import requests

from core.crypto import secret_store
from core.settings import settings

logger = logging.getLogger(__name__)

CONFIG_NAME = "notifications.json"
STATE_NAME = "notifications_state.json"
DISCORD_SECRET = "notify_discord_webhook"
SMTP_PASSWORD_SECRET = "notify_smtp_password"

EVENTS = {
    "apps": "An app keeps crashing or fails to start, and when it recovers",
    "vpn": "The VPN tunnel goes down or comes back",
    "tunnel": "The Cloudflare tunnel disconnects or reconnects",
    "updates": "A new appliance image or app update is available",
    "disk": "A storage volume is more than 90% full",
}
SECURITY = ("starttls", "ssl", "none")
DISK_ALERT_PERCENT = 90.0
DISK_CLEAR_PERCENT = 85.0
CHECK_SECONDS = 60
# A VPN or tunnel must be down for this many checks in a row before it is reported (reconnects are normal).
DOWN_CHECKS = 2

_DISCORD_WEBHOOK = re.compile(
    r"^https://(?:(?:ptb|canary)\.)?(?:discord\.com|discordapp\.com)/api/webhooks/\d+/[A-Za-z0-9_-]+$"
)
_EMAIL = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$")
_COLORS = {"problem": 0xE5484D, "ok": 0x30A46C, "info": 0x0A6CFF}


# --------------------------------------------------------------------------- settings


def _config_path() -> Path:
    return Path(settings.config_dir) / CONFIG_NAME


def _default_config() -> dict[str, Any]:
    return {
        "discord": {"enabled": False},
        "email": {
            "enabled": False,
            "host": "",
            "port": 587,
            "security": "starttls",
            "username": "",
            "sender": "",
            "recipients": [],
        },
        "events": {key: True for key in EVENTS},
    }


def load_config() -> dict[str, Any]:
    config = _default_config()
    try:
        data = json.loads(_config_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return config
    if not isinstance(data, dict):
        return config
    config["discord"]["enabled"] = bool((data.get("discord") or {}).get("enabled"))
    email = data.get("email") or {}
    config["email"].update(
        {
            "enabled": bool(email.get("enabled")),
            "host": str(email.get("host") or "")[:253],
            "port": _port(email.get("port")),
            "security": email.get("security") if email.get("security") in SECURITY else "starttls",
            "username": str(email.get("username") or "")[:200],
            "sender": str(email.get("sender") or "")[:200],
            "recipients": [r for r in (email.get("recipients") or []) if isinstance(r, str) and _EMAIL.match(r)][:10],
        }
    )
    events = data.get("events") or {}
    config["events"] = {key: bool(events.get(key, True)) for key in EVENTS}
    return config


def _port(value: Any) -> int:
    try:
        port = int(value)
    except (TypeError, ValueError):
        return 587
    return port if 1 <= port <= 65535 else 587


def parse_recipients(value: str | list[str]) -> list[str]:
    """Comma/space/semicolon separated addresses; raises ValueError naming the first bad one."""
    parts = value if isinstance(value, list) else re.split(r"[\s,;]+", value or "")
    out: list[str] = []
    for part in (p.strip() for p in parts):
        if not part:
            continue
        if not _EMAIL.match(part):
            raise ValueError(f"'{part}' is not an e-mail address.")
        if part not in out:
            out.append(part)
    if len(out) > 10:
        raise ValueError("Use at most 10 recipients.")
    return out


def validate_webhook(url: str) -> str:
    url = (url or "").strip()
    if not _DISCORD_WEBHOOK.match(url):
        raise ValueError("Use a Discord webhook URL (https://discord.com/api/webhooks/…).")
    return url


def save_config(
    *,
    discord_enabled: bool,
    webhook_url: str | None,
    email: dict[str, Any],
    smtp_password: str | None,
    events: dict[str, bool],
) -> dict[str, Any]:
    """Validate and store. ``None`` for a secret keeps the saved one, ``""`` removes it."""
    if webhook_url is not None:
        if webhook_url.strip():
            secret_store.save_secret(DISCORD_SECRET, validate_webhook(webhook_url))
        else:
            secret_store.delete_secret(DISCORD_SECRET)
    if discord_enabled and not _webhook():
        raise ValueError("Add a Discord webhook URL to turn Discord on.")

    security = email.get("security") or "starttls"
    if security not in SECURITY:
        raise ValueError("Security must be STARTTLS, SSL/TLS or none.")
    recipients = parse_recipients(email.get("recipients") or [])
    sender = str(email.get("sender") or "").strip()
    host = str(email.get("host") or "").strip()
    if smtp_password is not None:
        if smtp_password:
            secret_store.save_secret(SMTP_PASSWORD_SECRET, smtp_password)
        else:
            secret_store.delete_secret(SMTP_PASSWORD_SECRET)
    if email.get("enabled"):
        if not host:
            raise ValueError("Add the SMTP server to turn e-mail on.")
        if not recipients:
            raise ValueError("Add at least one recipient to turn e-mail on.")
        if sender and not _EMAIL.match(sender):
            raise ValueError("The sender must be an e-mail address.")

    config = {
        "discord": {"enabled": bool(discord_enabled)},
        "email": {
            "enabled": bool(email.get("enabled")),
            "host": host,
            "port": _port(email.get("port")),
            "security": security,
            "username": str(email.get("username") or "").strip(),
            "sender": sender,
            "recipients": recipients,
        },
        "events": {key: bool(events.get(key, True)) for key in EVENTS},
    }
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return public_config()


def _webhook() -> str:
    return (secret_store.get_secret(DISCORD_SECRET) or "").strip()


def public_config() -> dict[str, Any]:
    """The settings for the UI: secrets are only reported as present, never returned."""
    config = load_config()
    config["discord"]["webhook_saved"] = bool(_webhook())
    config["email"]["password_saved"] = bool(secret_store.get_secret(SMTP_PASSWORD_SECRET))
    config["event_labels"] = EVENTS
    return config


def any_channel_enabled(config: dict[str, Any] | None = None) -> bool:
    config = config or load_config()
    return bool(config["discord"]["enabled"] or config["email"]["enabled"])


# --------------------------------------------------------------------------- sending


def _instance_name() -> str:
    try:
        from core import branding

        return branding.public_branding().get("title") or "AIO Media Server Manager"
    except Exception:
        return "AIO Media Server Manager"


def send_discord(subject: str, body: str, level: str = "info") -> None:
    url = _webhook()
    if not url:
        raise ValueError("No Discord webhook saved.")
    payload = {
        "username": _instance_name()[:80],
        "embeds": [{"title": subject[:256], "description": body[:4000], "color": _COLORS.get(level, _COLORS["info"])}],
    }
    # ponytail: no redirects — the URL is pinned to Discord by validate_webhook.
    res = requests.post(url, json=payload, timeout=10, allow_redirects=False)
    if res.status_code >= 300:
        raise RuntimeError(f"Discord answered HTTP {res.status_code}.")


def send_email(subject: str, body: str, config: dict[str, Any] | None = None) -> None:
    email = (config or load_config())["email"]
    if not email["host"] or not email["recipients"]:
        raise ValueError("Set the SMTP server and at least one recipient first.")
    message = EmailMessage()
    message["Subject"] = f"[{_instance_name()}] {subject}"
    message["From"] = email["sender"] or email["username"] or email["recipients"][0]
    message["To"] = ", ".join(email["recipients"])
    message.set_content(body)
    password = secret_store.get_secret(SMTP_PASSWORD_SECRET) or ""
    context = ssl.create_default_context()
    if email["security"] == "ssl":
        client: smtplib.SMTP = smtplib.SMTP_SSL(email["host"], email["port"], timeout=15, context=context)
    else:
        client = smtplib.SMTP(email["host"], email["port"], timeout=15)
    with client:
        if email["security"] == "starttls":
            client.starttls(context=context)
        if email["username"]:
            client.login(email["username"], password)
        client.send_message(message)


def notify(event: str, subject: str, body: str, level: str = "info") -> list[str]:
    """Send to every enabled channel if ``event`` is switched on. Never raises; returns the failures."""
    config = load_config()
    if not config["events"].get(event, False):
        return []
    failures: list[str] = []
    if config["discord"]["enabled"]:
        try:
            send_discord(subject, body, level)
        except Exception as exc:
            failures.append(f"Discord: {exc}")
    if config["email"]["enabled"]:
        try:
            send_email(subject, body, config)
        except Exception as exc:
            failures.append(f"E-mail: {exc}")
    for failure in failures:
        logger.warning("Notification '%s' not sent — %s", subject, failure)
    return failures


def send_test(channel: str) -> None:
    subject = "Test notification"
    body = "Notifications from this appliance arrive here. You can change what is sent in Settings → Notifications."
    if channel == "discord":
        send_discord(subject, body, "info")
    elif channel == "email":
        send_email(subject, body)
    else:
        raise ValueError("Unknown channel.")


# --------------------------------------------------------------------------- watching


def snapshot(*, disks: bool = True) -> dict[str, Any]:
    """The facts the loop compares: sick apps, VPN/tunnel up, pending updates, full disks (a test write per data path; skip with disks=False)."""
    from core.cloudflare_tunnel import cloudflare_tunnel
    from core.supervisor import ProcessSupervisor
    from core.vpn import vpn_manager

    snap: dict[str, Any] = {"sick_apps": {}, "vpn_up": None, "tunnel_up": None, "updates": [], "full_disks": {}}
    try:
        for item in ProcessSupervisor.get().list_processes():
            if item.get("state") in {"crash_loop", "failed"}:
                snap["sick_apps"][item["name"]] = item.get("state")
    except Exception as exc:
        logger.debug("notifications: process list failed: %s", exc)
    if settings.vpn_enabled:
        try:
            snap["vpn_up"] = bool(vpn_manager.status().get("tunnel_up"))
        except Exception:
            snap["vpn_up"] = None
    if settings.cloudflare_tunnel_enabled:
        try:
            snap["tunnel_up"] = bool(cloudflare_tunnel.status().get("connected"))
        except Exception:
            snap["tunnel_up"] = None
    try:
        from core.update_schedule import scheduler

        status = scheduler.public_status()
        names = [f"{a.get('display_name') or a.get('name')} {a.get('latest_version') or ''}".strip() for a in status.get("available") or []]
        appliance = status.get("appliance") or {}
        if appliance.get("update_available"):
            names.append("Appliance image")
        snap["updates"] = sorted(names)
    except Exception as exc:
        logger.debug("notifications: update status failed: %s", exc)
    if not disks:
        return snap
    try:
        import psutil

        from core.storage import StorageManager

        for label, info in StorageManager(settings).validate_all().items():
            if info.exists:
                snap["full_disks"][label] = psutil.disk_usage(str(info.path)).percent
    except Exception as exc:
        logger.debug("notifications: disk check failed: %s", exc)
    return snap


class Watcher:
    """Turns two snapshots into messages. Kept free of I/O so the transitions are easy to test."""

    def __init__(self, notified_updates: list[str] | None = None) -> None:
        self.sick: set[str] = set()
        self.down_counts = {"vpn": 0, "tunnel": 0}
        self.reported_down = {"vpn": False, "tunnel": False}
        self.full: set[str] = set()
        self.notified_updates = list(notified_updates or [])

    def messages(self, snap: dict[str, Any]) -> list[tuple[str, str, str, str]]:
        out: list[tuple[str, str, str, str]] = []
        sick_now = dict(snap.get("sick_apps") or {})
        for name in sorted(set(sick_now) - self.sick):
            what = "keeps crashing" if sick_now[name] == "crash_loop" else "failed to start"
            out.append(("apps", f"{name} {what}", f"{name} {what}. Open Catalog for its logs, or restart it there.", "problem"))
        for name in sorted(self.sick - set(sick_now)):
            out.append(("apps", f"{name} is running again", f"{name} recovered and is running.", "ok"))
        self.sick = set(sick_now)

        for key, label, event in (("vpn_up", "VPN", "vpn"), ("tunnel_up", "Cloudflare tunnel", "tunnel")):
            up = snap.get(key)
            if up is None:
                continue
            if up:
                if self.reported_down[event]:
                    out.append((event, f"{label} is back", f"The {label} is connected again.", "ok"))
                self.down_counts[event] = 0
                self.reported_down[event] = False
                continue
            self.down_counts[event] += 1
            if self.down_counts[event] >= DOWN_CHECKS and not self.reported_down[event]:
                body = (
                    "The VPN tunnel is down, so the apps that only download through it are stopped until it reconnects."
                    if event == "vpn"
                    else "The Cloudflare tunnel is not connected, so your public addresses are unreachable."
                )
                out.append((event, f"{label} is down", body, "problem"))
                self.reported_down[event] = True

        updates = list(snap.get("updates") or [])
        new = [u for u in updates if u not in self.notified_updates]
        if new:
            out.append(("updates", "Updates available", "New versions are ready:\n" + "\n".join(f"• {u}" for u in new) + "\nSee Settings → Updates.", "info"))
        self.notified_updates = updates

        for label, percent in sorted((snap.get("full_disks") or {}).items()):
            if percent >= DISK_ALERT_PERCENT and label not in self.full:
                out.append(("disk", f"{label} storage is {percent:.0f}% full", f"The {label} volume is {percent:.0f}% full. Free some space before downloads and imports start failing.", "problem"))
                self.full.add(label)
            elif percent < DISK_CLEAR_PERCENT and label in self.full:
                self.full.discard(label)
        return out


def _state_path() -> Path:
    return Path(settings.config_dir) / STATE_NAME


def _load_notified_updates() -> list[str]:
    try:
        data = json.loads(_state_path().read_text(encoding="utf-8"))
        return [u for u in data.get("notified_updates") or [] if isinstance(u, str)]
    except (OSError, ValueError, AttributeError):
        return []


def _save_notified_updates(updates: list[str]) -> None:
    try:
        _state_path().write_text(json.dumps({"notified_updates": updates, "saved_at": int(time.time())}), encoding="utf-8")
    except OSError as exc:
        logger.debug("notifications: could not save state: %s", exc)


async def notifications_loop() -> None:
    """Every minute: compare the appliance state and send what changed."""
    watcher = Watcher(_load_notified_updates())
    await asyncio.sleep(CHECK_SECONDS)  # let apps, VPN and tunnel come up first
    while True:
        try:
            if any_channel_enabled():
                snap = await asyncio.to_thread(snapshot)
                before = list(watcher.notified_updates)
                for event, subject, body, level in watcher.messages(snap):
                    await asyncio.to_thread(notify, event, subject, body, level)
                if watcher.notified_updates != before:
                    await asyncio.to_thread(_save_notified_updates, watcher.notified_updates)
        except Exception as exc:  # the loop must survive anything
            logger.warning("Notifications check failed: %s", exc)
        await asyncio.sleep(CHECK_SECONDS)
